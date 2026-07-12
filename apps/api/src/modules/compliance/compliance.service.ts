import { Injectable } from "@nestjs/common";
import type { ComplianceAnswer, ProductStructure, QueryAnalysis, RetrievalHit } from "@otc/shared";
import { LlmService } from "../llm/llm.service";
import { RetrievalService } from "../retrieval/retrieval.service";
import { QueryAnalysisService } from "../query-analysis/query-analysis.service";
import { ContextBuilderService } from "../context-builder/context-builder.service";
import { CitationValidatorService } from "../citation-validator/citation-validator.service";
import { PromptService } from "../prompt/prompt.service";

export type SSEEvent =
  | { type: "thinking"; message: string }
  | { type: "retrieving"; count: number }
  | { type: "product_structure"; data: ProductStructure }
  | { type: "answer_chunk"; content: string }
  | { type: "answer"; data: ComplianceAnswer }
  | { type: "hits"; hits: RetrievalHit[] }
  | { type: "error"; message: string }
  | { type: "done" };

@Injectable()
export class ComplianceService {
  constructor(
    private readonly llm: LlmService,
    private readonly retrieval: RetrievalService,
    private readonly queryAnalysis: QueryAnalysisService,
    private readonly contextBuilder: ContextBuilderService,
    private readonly citationValidator: CitationValidatorService,
    private readonly promptService: PromptService,
  ) {}

  async answer(query: string) {
    const analysis = this.queryAnalysis.analyze(query);
    const hits = await this.retrieval.search(analysis);
    const structure = this.structureFromAnalysis(analysis);
    const draft = this.llm.isConfigured
      ? await this.generateEvidenceBoundAnswer(query, analysis, structure, hits)
      : this.insufficientAnswer(structure, hits, "未配置LLM_API_KEY，系统只完成了检索，未调用回答模型");
    const answer = this.citationValidator.validate(draft, hits, analysis);
    return { answer, hits, queryAnalysis: analysis };
  }

  async *answerStream(query: string): AsyncGenerator<SSEEvent, void, unknown> {
    try {
      yield { type: "thinking", message: "正在规范化问题并拆解检索任务..." };
      const result = await this.answer(query);
      yield { type: "product_structure", data: result.answer.productStructure };
      yield { type: "retrieving", count: result.hits.length };
      yield { type: "hits", hits: result.hits };
      yield { type: "answer", data: result.answer };
    } catch (error) {
      yield { type: "error", message: error instanceof Error ? error.message : "问答链路异常" };
    } finally {
      yield { type: "done" };
    }
  }

  private async generateEvidenceBoundAnswer(query: string, analysis: QueryAnalysis, structure: ProductStructure, hits: RetrievalHit[]): Promise<ComplianceAnswer> {
    if (!hits.length) return this.insufficientAnswer(structure, hits, "未检索到直接相关的法规片段");
    const prompt = `你是中国场外衍生品法规问答助手。你只能依据下面的“本次检索证据”回答，禁止使用模型记忆补充法规、文号、条款或URL。

规则：
1. 每个重要结论必须引用一个或多个 evidence_id；不得先给结论再附不匹配的法规。
2. 区分【明确规定】【基于法规的推导】【需结合具体业务判断】【证据不足】。
3. status为空或unknown时，不得断言法规现行有效；废止/失效文件不得作为现行依据。
4. 证据不足时，结论必须包含“根据当前知识库检索结果，暂时无法形成确定结论。”
5. 仅输出JSON，不得输出Markdown代码围栏。格式：
{"conclusion":"...","conclusionLabel":"可做|不可做|有条件可做|需人工合规复核","regulatoryBasis":[{"evidenceId":"chunk_...","requirement":"该证据直接支持的结论"}],"restrictions":["..."],"missingInfo":["..."],"manualReviewNote":"..."}

用户问题：${query}
问题分析：${JSON.stringify(analysis)}
本次检索证据：
${this.contextBuilder.build(hits)}`;
    const raw = await this.llm.chat(this.promptService.getComplianceAgentPrompt(), prompt, 120000);
    const parsed = this.parseJson(raw);
    const basis = Array.isArray(parsed.regulatoryBasis) ? parsed.regulatoryBasis : [];
    return {
      conclusion: String(parsed.conclusion || "【证据不足】根据当前知识库检索结果，暂时无法形成确定结论。"),
      conclusionLabel: ["可做", "不可做", "有条件可做", "需人工合规复核"].includes(parsed.conclusionLabel) ? parsed.conclusionLabel : "需人工合规复核",
      productStructure: structure,
      regulatoryBasis: basis.map((item: any) => ({ evidenceId: String(item.evidenceId || ""), title: "", publisher: "", url: "", articleNo: "", excerpt: "", requirement: String(item.requirement || ""), status: "" })),
      restrictions: Array.isArray(parsed.restrictions) ? parsed.restrictions.map(String) : [],
      missingInfo: Array.isArray(parsed.missingInfo) ? parsed.missingInfo.map(String) : [],
      manualReviewNote: String(parsed.manualReviewNote || ""),
      confidenceScore: basis.length ? "medium" : "low",
      confidenceReason: basis.length ? "回答包含可校验的证据ID，仍需通过引用校验" : "模型未返回证据ID",
      retrievalTrace: this.retrievalTrace(hits),
    };
  }

  private insufficientAnswer(structure: ProductStructure, hits: RetrievalHit[], reason: string): ComplianceAnswer {
    return {
      conclusion: "【证据不足】根据当前知识库检索结果，暂时无法形成确定结论。",
      conclusionLabel: "需人工合规复核",
      productStructure: structure,
      regulatoryBasis: [],
      restrictions: [],
      missingInfo: [reason],
      manualReviewNote: "当前只能展示检索线索，不能据此形成确定性法律结论。",
      confidenceScore: "low",
      confidenceReason: reason,
      retrievalTrace: this.retrievalTrace(hits),
    };
  }

  private structureFromAnalysis(analysis: QueryAnalysis): ProductStructure {
    return {
      underlyingAsset: "",
      productType: analysis.productTypes.join("、"),
      transactionStructure: analysis.normalizedQuery.includes("雪球") ? "雪球/自动赎回结构" : "",
      counterparty: analysis.subjects.join("、"),
      investorType: analysis.subjects.filter((value) => /投资者|基金|资管/.test(value)).join("、"),
      isCrossBorder: /跨境|境外|外汇/.test(analysis.normalizedQuery),
      riskPoints: analysis.topics.filter((value) => /风控|适当性|禁止|披露/.test(value)),
      missingInfo: [],
    };
  }

  private retrievalTrace(hits: RetrievalHit[]) {
    const hasVector = hits.some((hit) => hit.retrievalMethods.includes("vector"));
    return {
      evidenceHits: hits.length,
      clauseHits: hits.length,
      documentHits: new Set(hits.map((hit) => hit.documentId)).size,
      strategy: hasVector ? "query-analysis + BM25 + BGE + equal-weight RRF" : "query-analysis + BM25 (vector model unavailable)",
    };
  }

  private parseJson(raw: string): any {
    const cleaned = raw.replace(/```(?:json)?/gi, "").replace(/```/g, "").trim();
    const start = cleaned.indexOf("{");
    const end = cleaned.lastIndexOf("}");
    if (start < 0 || end < start) throw new Error("回答模型未返回合法JSON");
    return JSON.parse(cleaned.slice(start, end + 1));
  }
}
