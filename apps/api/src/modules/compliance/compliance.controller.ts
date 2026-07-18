import { Body, Controller, Get, Post, Res } from "@nestjs/common";
import { complianceQueryInputSchema } from "@otc/shared";
import { fail, ok } from "../../common/api-response";
import { RetrievalService } from "../retrieval/retrieval.service";
import { ComplianceService } from "./compliance.service";
import { AgentRunError } from "./regulatory-agent.service";

type ExpressResponse = {
  status: (code: number) => ExpressResponse;
  json: (body: unknown) => void;
  setHeader: (name: string, value: string) => void;
  flushHeaders: () => void;
  write: (chunk: string) => void;
  end: () => void;
  once: (event: "close", listener: () => void) => void;
  off: (event: "close", listener: () => void) => void;
  writableEnded: boolean;
  flush?: () => void;
};

@Controller("compliance")
export class ComplianceController {
  constructor(
    private readonly compliance: ComplianceService,
    private readonly retrieval: RetrievalService,
  ) {}

  @Post("query")
  async query(@Body() body: unknown, @Res({ passthrough: true }) res: ExpressResponse) {
    const parsed = complianceQueryInputSchema.safeParse(body);
    if (!parsed.success) {
      res.status(400);
      return fail(parsed.error.issues[0]?.message ?? "请求参数有误", "INVALID_REQUEST");
    }

    if (!this.retrieval.isReady) {
      res.status(503);
      return fail("知识库索引尚未加载完成，请稍后重试", "INDEX_NOT_READY");
    }

    try {
      const result = await this.compliance.answer(parsed.data.message, {
        sessionId: parsed.data.sessionId,
        debug: parsed.data.debug,
      });
      return ok(result);
    } catch (error) {
      const details = this.errorDetails(error);
      res.status(details.status);
      console.error("[ComplianceController] POST /compliance/query error:", error);
      return fail(details.message, details.code);
    }
  }

  @Post("query/stream")
  async queryStream(@Body() body: unknown, @Res() res: ExpressResponse) {
    const parsed = complianceQueryInputSchema.safeParse(body);
    if (!parsed.success) {
      res.status(400).json({
        success: false,
        error: { message: parsed.error.issues[0]?.message ?? "请求参数有误", code: "INVALID_REQUEST" },
      });
      return;
    }

    if (!this.retrieval.isReady) {
      res.status(503).json({
        success: false,
        error: { message: "知识库索引尚未加载完成，请稍后重试", code: "INDEX_NOT_READY" },
      });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders();

    const abortController = new AbortController();
    let aborted = false;
    const handleClose = () => {
      if (res.writableEnded) return;
      aborted = true;
      abortController.abort();
    };
    res.once("close", handleClose);

    try {
      const stream = this.compliance.answerStream(parsed.data.message, {
        sessionId: parsed.data.sessionId,
        debug: parsed.data.debug,
        signal: abortController.signal,
      });

      for await (const event of stream) {
        if (aborted) break;
        res.write(`data: ${JSON.stringify(event)}\n\n`);
        res.flush?.();
        if (event.type === "done" || event.type === "error") break;
      }
    } catch (error) {
      if (!aborted) {
        const details = this.errorDetails(error);
        console.error("[ComplianceController] POST /compliance/query/stream error:", error);
        try {
          res.write(`data: ${JSON.stringify({ type: "error", message: details.message, code: details.code })}\n\n`);
        } catch {
          // The client may have disconnected between the check and write.
        }
      }
    } finally {
      res.off("close", handleClose);
      if (!aborted) res.end();
    }
  }

  @Get("health")
  health() {
    return ok({
      status: this.retrieval.isReady ? "ok" : "starting",
      indexReady: this.retrieval.isReady,
      stats: this.retrieval.stats,
    });
  }

  private errorDetails(error: unknown) {
    if (error instanceof AgentRunError) {
      return { status: error.httpStatus, code: error.code, message: error.message };
    }
    return {
      status: 500,
      code: "INTERNAL_ERROR",
      message: error instanceof Error ? error.message : "合规查询失败",
    };
  }
}
