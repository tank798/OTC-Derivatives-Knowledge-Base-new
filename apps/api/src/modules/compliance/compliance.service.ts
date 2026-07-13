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
    let answer = this.citationValidator.validate(draft, hits, analysis);
    if (this.llm.isConfigured && answer.citationValidation?.passed === false) {
      const repairedDraft = await this.generateEvidenceBoundAnswer(
        query,
        analysis,
        structure,
        hits,
        { previousDraft: draft, validationIssues: answer.citationValidation.issues },
      );
      answer = this.citationValidator.validate(repairedDraft, hits, analysis);
    }
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

  private async generateEvidenceBoundAnswer(
    query: string,
    analysis: QueryAnalysis,
    structure: ProductStructure,
    hits: RetrievalHit[],
    repair?: { previousDraft: ComplianceAnswer; validationIssues: string[] },
  ): Promise<ComplianceAnswer> {
    if (!hits.length) return this.insufficientAnswer(structure, hits, "未检索到直接相关的法规片段");
    const prompt = `你是中国场外衍生品法规问答助手。你只能依据下面的“本次检索证据”回答，禁止使用模型记忆补充法规、文号、条款或URL。

规则：
1. 每个重要结论必须引用一个或多个 evidence_id；不得先给结论再附不匹配的法规。
2. 区分【明确规定】【基于法规的推导】【需结合具体业务判断】【证据不足】。
3. status为空或unknown时，不得断言法规现行有效；废止/失效文件不得作为现行依据。
4. 证据不足时，结论必须包含“根据当前知识库检索结果，暂时无法形成确定结论。”
5. 已公布但尚未施行的文件只能用于说明未来规则及生效时点，不得当作当前已生效依据。
6. 不得把同一条中不同款、项针对不同产品或交易的条件交叉套用。
7. 在 conclusion 或 restrictions 中提到的每一份法规，都必须在 regulatoryBasis 中选择对应 evidence_id；不得只在文字里提到而不引用。
8. 对“可以吗”这类未限定范围的问题：如果证据显示至少一条重要现行交易路径被明确禁止，directAnswer 应填“否”，含义是“不能笼统认定可以”，随后必须说明禁止范围；不得据此扩大成所有主体、所有时间一律禁止。
9. 仅输出JSON，不得输出Markdown代码围栏。格式：
{"directAnswer":"是|否|不能确认","conclusion":"...","conclusionLabel":"可做|不可做|有条件可做|需人工合规复核","regulatoryBasis":[{"evidenceId":"chunk_...","requirement":"该证据直接支持的结论"}],"restrictions":["..."],"missingInfo":["..."],"manualReviewNote":"..."}

回答顺序要求：
- 先给 directAnswer。问题能够由直接条文明确回答时，只能填“是”或“否”；证据不足以作二元判断时填“不能确认”。
- conclusion 紧接 directAnswer 解释判断，不得先铺陈背景，也不要重复“是、否、不能确认”本身。例如 directAnswer 为“否”时，conclusion 写“不能笼统认定可以……”。
- 然后再列 regulatoryBasis。模型只选择 evidence_id；法规标题、条款、效力状态和官网URL由系统按证据回填。

用户问题：${query}
问题分析：${JSON.stringify(analysis)}
${repair ? `上一次回答未通过系统引用校验。请依据同一批证据修订，不得机械服从错误反馈，也不得新增证据中不存在的事实。\n上一次回答：${JSON.stringify(repair.previousDraft)}\n校验问题：${repair.validationIssues.join("；")}\n修订要求：若缺少直接授权条文，应将 directAnswer 改为“不能确认”并明确说明证据边界；若遗漏已经在证据中的必要法规，应在核对原文后补选其 evidence_id；所有提及的法规都必须正式引用。` : ""}
本次检索证据：
${this.contextBuilder.build(hits)}`;
    const raw = await this.llm.chat(this.promptService.getComplianceAgentPrompt(), prompt, 120000);
    const parsed = this.parseJson(raw);
    const basis = Array.isArray(parsed.regulatoryBasis) ? parsed.regulatoryBasis : [];
    return {
      directAnswer: ["是", "否", "不能确认"].includes(parsed.directAnswer) ? parsed.directAnswer : "不能确认",
      conclusion: this.stripRepeatedDecision(
        String(parsed.conclusion || "【证据不足】根据当前知识库检索结果，暂时无法形成确定结论。"),
        ["是", "否", "不能确认"].includes(parsed.directAnswer) ? parsed.directAnswer : "不能确认",
      ),
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
      directAnswer: "不能确认",
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
      chunkHits: hits.length,
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

  private stripRepeatedDecision(conclusion: string, directAnswer: string) {
    return conclusion.replace(new RegExp(`^${directAnswer}[，,。；;：:\\s]+`), "").trim();
  }
}
