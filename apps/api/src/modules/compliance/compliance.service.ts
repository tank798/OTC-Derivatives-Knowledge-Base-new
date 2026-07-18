import { Injectable } from "@nestjs/common";
import type { AgentChatResponse, AgentProgressEvent, AgentRegulatoryAnswer, RetrievalHit } from "@otc/shared";
import { AgentRunError, RegulatoryAgentService } from "./regulatory-agent.service";

export type SSEEvent =
  | { type: "progress"; data: AgentProgressEvent }
  | { type: "message"; data: AgentChatResponse }
  | { type: "answer"; data: AgentRegulatoryAnswer }
  | { type: "hits"; hits: RetrievalHit[] }
  | { type: "error"; message: string; code?: string }
  | { type: "done" };

@Injectable()
export class ComplianceService {
  constructor(private readonly agent: RegulatoryAgentService) {}

  answer(message: string, options: {
    sessionId?: string;
    debug?: boolean;
    onProgress?: (event: AgentProgressEvent) => void;
    signal?: AbortSignal;
  } = {}) {
    return this.agent.run(message, options);
  }

  async *answerStream(
    message: string,
    options: { sessionId?: string; debug?: boolean; signal?: AbortSignal } = {},
  ): AsyncGenerator<SSEEvent, void, unknown> {
    const queue: SSEEvent[] = [];
    let wake: (() => void) | null = null;
    let settled = false;
    let result: AgentChatResponse | undefined;
    let failure: unknown;
    const push = (event: SSEEvent) => {
      queue.push(event);
      const resume = wake;
      wake = null;
      resume?.();
    };

    void this.answer(message, {
      ...options,
      onProgress: (event) => push({ type: "progress", data: event }),
    }).then((value) => {
      result = value;
    }).catch((error) => {
      failure = error;
    }).finally(() => {
      settled = true;
      const resume = wake;
      wake = null;
      resume?.();
    });

    while (!settled || queue.length) {
      if (queue.length) {
        yield queue.shift()!;
        continue;
      }
      await new Promise<void>((resolve) => {
        wake = resolve;
      });
    }

    try {
      if (failure) throw failure;
      if (!result) throw new Error("法规 Agent 未返回结果");
      yield { type: "message", data: result };
      if (result.hits.length) yield { type: "hits", hits: result.hits };
      if (result.answer) yield { type: "answer", data: result.answer };
    } catch (error) {
      yield {
        type: "error",
        message: error instanceof Error ? error.message : "法规 Agent 执行异常",
        ...(error instanceof AgentRunError ? { code: error.code } : {}),
      };
    } finally {
      yield { type: "done" };
    }
  }
}
