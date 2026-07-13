import { Injectable } from "@nestjs/common";
import type { RetrievalHit } from "@otc/shared";

@Injectable()
export class ContextBuilderService {
  build(hits: RetrievalHit[], options: { includeQuoteCandidates?: boolean } = {}): string {
    if (!hits.length) return "（本次检索未返回可用法规证据）";
    return hits.map((hit, index) => [
      `【证据 ${index + 1}】`,
      `evidence_id: ${hit.id}`,
      `document_id: ${hit.documentId}`,
      `chunk_id: ${hit.chunkId}`,
      `法规名称: ${hit.title}`,
      `发文主体: ${hit.publisher || "未标注"}`,
      `文号: ${hit.documentNumber || "未标注"}`,
      `发布日期: ${hit.publishedAt || "未标注"}`,
      `施行日期: ${hit.effectiveAt || "未标注"}`,
      `效力状态: ${hit.status || "unknown"}`,
      `章节: ${hit.chapterTitle || "未标注"}`,
      `条款: ${[hit.articleNo, hit.articleEnd].filter(Boolean).join("至") || "未标注"}`,
      `官网URL: ${hit.url || "未提供"}`,
      `本地来源: ${hit.localFilePath}`,
      `检索方式: ${hit.retrievalMethods.join(" + ")}`,
      `相关性分数: ${hit.score.toFixed(6)}`,
      ...(options.includeQuoteCandidates ? [
        "系统截取的连续原文候选(可以逐字复制为quoteExact):",
        ...this.quoteCandidates(hit.text).map((candidate, candidateIndex) => `quote_candidate_${candidateIndex + 1}: ${JSON.stringify(candidate)}`),
      ] : []),
      `完整原文:\n${hit.text}`,
    ].join("\n")).join("\n\n");
  }

  private quoteCandidates(text: string): string[] {
    const candidates = (text.match(/[^\u3002；;]+[\u3002；;]?/g) ?? [])
      .map((value) => value.trim())
      .filter((value) => value.length >= 12 && value.length <= 650 && text.includes(value));
    const priority = /不得|应当|必须|仅限|除外|例外|敲入|敲出|雪球|本公司股票|25%|1000万|尚未施行/;
    return [...new Set(candidates)]
      .sort((a, b) => Number(priority.test(b)) - Number(priority.test(a)) || a.length - b.length)
      .slice(0, 3);
  }
}
