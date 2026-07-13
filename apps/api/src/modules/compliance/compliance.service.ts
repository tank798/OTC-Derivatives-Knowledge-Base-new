import { Injectable } from "@nestjs/common";
import type { ProductStructure, RetrievalHit } from "@otc/shared";
import { AgentWorkflowService } from "./agent-workflow.service";

export type SSEEvent =
  | { type: "thinking"; message: string }
  | { type: "retrieving"; count: number }
  | { type: "product_structure"; data: ProductStructure }
  | { type: "answer_chunk"; content: string }
  | { type: "answer"; data: Awaited<ReturnType<AgentWorkflowService["run"]>>["answer"] }
  | { type: "hits"; hits: RetrievalHit[] }
  | { type: "error"; message: string }
  | { type: "done" };

@Injectable()
export class ComplianceService {
  constructor(private readonly workflow: AgentWorkflowService) {}

  answer(query: string, options: { debug?: boolean } = {}) {
    return this.workflow.run(query, options);
  }

  async *answerStream(query: string): AsyncGenerator<SSEEvent, void, unknown> {
    try {
      yield { type: "thinking", message: "正在分析问题并制定法规检索计划…" };
      const result = await this.answer(query);
      yield { type: "product_structure", data: result.answer.productStructure };
      yield { type: "retrieving", count: result.hits.length };
      yield { type: "hits", hits: result.hits };
      yield { type: "answer", data: result.answer };
    } catch (error) {
      yield { type: "error", message: error instanceof Error ? error.message : "受控法规智能体执行异常" };
    } finally {
      yield { type: "done" };
    }
  }
}
