import { Injectable } from "@nestjs/common";
import { hybridSearchInputSchema } from "@otc/shared";
import type { HybridSearchInput, RetrievalHit } from "@otc/shared";
import { RetrievalService } from "../retrieval/retrieval.service";

export type HybridSearchToolResult =
  | { ok: true; tool: "hybrid_regulation_search"; input: HybridSearchInput; hits: RetrievalHit[] }
  | { ok: false; tool: "hybrid_regulation_search"; error: string; hits: [] };

/** Read-only semantic tool. The harness validates every model-produced input. */
@Injectable()
export class HybridRegulationSearchTool {
  readonly name = "hybrid_regulation_search" as const;
  readonly permission = "ALLOW_READ_ONLY" as const;
  readonly description = "使用现有 BM25、本地 BGE、等权 RRF、去重和必要上下文补齐检索法规 Chunk。";

  constructor(private readonly retrieval: RetrievalService) {}

  async execute(rawInput: unknown): Promise<HybridSearchToolResult> {
    const parsed = hybridSearchInputSchema.safeParse(rawInput);
    if (!parsed.success) {
      return {
        ok: false,
        tool: this.name,
        error: `检索工具参数无效: ${parsed.error.issues.map((issue) => issue.message).join("；")}`,
        hits: [],
      };
    }
    try {
      const hits = await this.retrieval.hybridSearch(parsed.data);
      return { ok: true, tool: this.name, input: parsed.data, hits };
    } catch (error) {
      return {
        ok: false,
        tool: this.name,
        error: error instanceof Error ? error.message : "混合检索工具执行失败",
        hits: [],
      };
    }
  }
}
