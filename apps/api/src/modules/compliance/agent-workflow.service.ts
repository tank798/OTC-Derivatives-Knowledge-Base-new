import { Injectable } from "@nestjs/common";
import { z } from "zod";
import { evidenceAssessmentSchema, retrievalPlanSchema } from "@otc/shared";
import type {
  AgentState,
  AgentTrace,
  AnswerReview,
  ComplianceAnswer,
  EvidenceAssessment,
  QueryAnalysis,
  RetrievalHit,
  RetrievalPlan,
} from "@otc/shared";
import { LlmService } from "../llm/llm.service";
import { QueryAnalysisService } from "../query-analysis/query-analysis.service";
import { ContextBuilderService } from "../context-builder/context-builder.service";
import { CitationValidatorService } from "../citation-validator/citation-validator.service";
import { PromptService } from "../prompt/prompt.service";
import { HybridRegulationSearchTool } from "./hybrid-regulation-search.tool";

const MAX_RETRIEVAL_ROUNDS = 2;
const MAX_REPAIRS = 1;
const MAX_REVIEWS = 2;
const MAX_TRANSITIONS = 24;

const reviewStringSchema = z.preprocess((value) => {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["instruction", "action", "reason", "query", "description", "type"]) {
      if (typeof record[key] === "string") return record[key];
    }
    return JSON.stringify(value);
  }
  return String(value ?? "");
}, z.string());

const answerReviewValidationSchema = z.object({
  verdict: z.enum(["PASS", "REPAIR", "RETRIEVE"]),
  issues: z.array(z.object({
    type: z.string(), severity: z.enum(["MINOR", "MAJOR", "CRITICAL"]), statement: z.string(),
    evidenceId: z.string().default(""), reason: z.string(), action: z.string(),
  })).default([]),
  repairInstructions: z.array(reviewStringSchema).default([]), missingEvidence: z.array(reviewStringSchema).default([]),
  followUpQueries: z.array(reviewStringSchema).max(12).default([]),
});

const modelAnswerSchema = z.object({
  directAnswer: z.preprocess((value) => {
    const text = String(value ?? "").trim();
    if (text.startsWith("不能确认")) return "不能确认";
    if (text.startsWith("否")) return "否";
    if (text.startsWith("是")) return "是";
    return value;
  }, z.enum(["是", "否", "不能确认"])),
  conclusionLevel: z.enum(["明确规定", "基于法规的推导", "证据不足"]),
  conclusion: z.string().min(1),
  scope: z.object({
    subject: z.string().default(""), product: z.string().default(""),
    counterparty: z.string().default(""), time: z.string().default(""),
    conditions: z.array(z.string()).default([]),
  }),
  regulatoryBasis: z.array(z.object({
    evidenceId: z.string().min(1), quoteExact: z.string().min(1), supports: z.string().min(1),
  })).default([]),
  restrictions: z.array(z.string()).default([]),
  missingInfo: z.array(z.string()).default([]),
  manualReviewNote: z.string().default(""),
  confidence: z.enum(["high", "medium", "low"]).default("low"),
});

type TraceEntry = AgentTrace["states"][number];
type RepairRequest = { source: "deterministic" | "review"; instructions: string[]; retrieve: boolean };

interface WorkflowContext {
  query: string;
  debug: boolean;
  state: AgentState;
  fallbackAnalysis: QueryAnalysis;
  analysis: QueryAnalysis;
  plan: RetrievalPlan | null;
  assessment: EvidenceAssessment | null;
  hits: RetrievalHit[];
  draft: ComplianceAnswer | null;
  answer: ComplianceAnswer | null;
  review: AnswerReview | null;
  repairRequest: RepairRequest | null;
  trace: TraceEntry[];
  retrievalRounds: number;
  repairCount: number;
  reviewCount: number;
  llmCalls: number;
  degraded: boolean;
  degradationReason: string;
}

@Injectable()
export class AgentWorkflowService {
  constructor(
    private readonly llm: LlmService,
    private readonly queryAnalysis: QueryAnalysisService,
    private readonly contextBuilder: ContextBuilderService,
    private readonly validator: CitationValidatorService,
    private readonly prompts: PromptService,
    private readonly searchTool: HybridRegulationSearchTool,
  ) {}

  async run(query: string, options: { debug?: boolean } = {}) {
    const fallbackAnalysis = this.queryAnalysis.analyze(query);
    const ctx: WorkflowContext = {
      query, debug: Boolean(options.debug), state: "ANALYZE_QUERY",
      fallbackAnalysis, analysis: fallbackAnalysis, plan: null, assessment: null,
      hits: [], draft: null, answer: null, review: null, repairRequest: null, trace: [],
      retrievalRounds: 0, repairCount: 0, reviewCount: 0, llmCalls: 0,
      degraded: false, degradationReason: "",
    };

    for (let transitions = 0; transitions < MAX_TRANSITIONS && ctx.state !== "FINALIZE"; transitions += 1) {
      await this.step(ctx);
    }
    if (ctx.state !== "FINALIZE") this.degrade(ctx, "智能体达到最大状态转换次数");
    if (!ctx.answer) ctx.answer = this.insufficientAnswer(ctx.analysis, ctx.hits, ctx.degradationReason || "无可用回答");

    const agentTrace: AgentTrace = {
      states: ctx.trace,
      retrievalRounds: ctx.retrievalRounds,
      repairCount: ctx.repairCount,
      reviewCount: ctx.reviewCount,
      llmCalls: ctx.llmCalls,
      model: this.llm.modelName,
      degraded: ctx.degraded,
      ...(ctx.degradationReason ? { degradationReason: ctx.degradationReason } : {}),
    };
    return {
      answer: ctx.answer,
      hits: ctx.hits,
      queryAnalysis: ctx.analysis,
      ...(ctx.debug ? {
        retrievalPlan: ctx.plan ?? undefined,
        evidenceAssessment: ctx.assessment ?? undefined,
        reviewResult: ctx.review ?? undefined,
        agentTrace,
      } : {}),
    };
  }

  private async step(ctx: WorkflowContext) {
    switch (ctx.state) {
      case "ANALYZE_QUERY":
        this.record(ctx, "ANALYZE_QUERY", "完成基础规范化，规则分析仅用于安全兜底");
        ctx.state = "PLAN_RETRIEVAL";
        return;
      case "PLAN_RETRIEVAL":
        ctx.plan = await this.planRetrieval(ctx);
        ctx.analysis = this.analysisFromPlan(ctx.fallbackAnalysis, ctx.plan);
        this.record(ctx, "PLAN_RETRIEVAL", `${ctx.plan.fallbackUsed ? "降级" : "模型"}计划包含 ${ctx.plan.subQuestions.length} 个子问题`);
        ctx.state = "RETRIEVE";
        return;
      case "RETRIEVE":
      case "RETRIEVE_AGAIN":
        await this.retrieve(ctx);
        ctx.state = "ASSESS_EVIDENCE";
        return;
      case "ASSESS_EVIDENCE":
        ctx.assessment = await this.assessEvidence(ctx);
        this.record(ctx, "ASSESS_EVIDENCE", ctx.assessment.reasonSummary, ctx.retrievalRounds);
        if (!ctx.assessment.sufficient && ctx.retrievalRounds < MAX_RETRIEVAL_ROUNDS && ctx.assessment.followUpQueries.length) {
          ctx.plan = this.followUpPlan(ctx.plan!, ctx.assessment);
          ctx.state = "RETRIEVE_AGAIN";
        } else {
          ctx.state = "DRAFT_ANSWER";
        }
        return;
      case "DRAFT_ANSWER":
        if (!this.llm.isConfigured) {
          this.degrade(ctx, "未配置 LLM_API_KEY，系统只完成了规则降级分析和混合检索");
          return;
        }
        try {
          ctx.draft = await this.generateAnswer(ctx);
        } catch (error) {
          this.degrade(ctx, `回答模型输出无法通过结构化校验: ${error instanceof Error ? error.message : "未知错误"}`);
          return;
        }
        this.record(ctx, "DRAFT_ANSWER", ctx.repairCount ? "已按约束修订候选回答" : "已仅根据最终证据生成候选回答");
        ctx.state = "VERIFY_DETERMINISTICALLY";
        return;
      case "VERIFY_DETERMINISTICALLY": {
        if (!ctx.draft) { this.degrade(ctx, "候选回答不存在"); return; }
        ctx.draft = this.snapQuotesToOriginal(ctx.draft, ctx.hits);
        ctx.answer = this.validator.validate(ctx.draft, ctx.hits, ctx.analysis);
        const passed = ctx.answer.citationValidation?.passed === true;
        this.record(ctx, "VERIFY_DETERMINISTICALLY", passed ? "evidence_id、逐字引文、元数据和效力校验通过" : `校验失败: ${ctx.answer.citationValidation?.issues.join("；")}`);
        if (passed) ctx.state = "REVIEW_ANSWER";
        else if (ctx.repairCount < MAX_REPAIRS) {
          ctx.repairRequest = { source: "deterministic", instructions: ctx.answer.citationValidation?.issues ?? [], retrieve: false };
          ctx.state = "REPAIR_OR_RETRIEVE";
        } else this.degrade(ctx, "程序化真实性校验在一次修订后仍未通过", ctx.answer);
        return;
      }
      case "REVIEW_ANSWER": {
        if (!ctx.answer) { this.degrade(ctx, "没有可供独立审查的回答"); return; }
        if (ctx.reviewCount >= MAX_REVIEWS) { this.degrade(ctx, "独立审查超过上限", ctx.answer); return; }
        ctx.review = await this.reviewAnswer(ctx);
        ctx.reviewCount += 1;
        this.record(ctx, "REVIEW_ANSWER", `独立审查结果: ${ctx.review.verdict}`);
        if (ctx.review.verdict === "PASS") {
          ctx.answer = { ...ctx.answer, reviewValidation: { passed: true, verdict: "PASS" } };
          ctx.state = "FINALIZE";
        } else if (ctx.repairCount < MAX_REPAIRS) {
          ctx.repairRequest = {
            source: "review",
            instructions: [...ctx.review.repairInstructions, ...ctx.review.issues.map((issue) => issue.reason)],
            retrieve: ctx.review.verdict === "RETRIEVE",
          };
          ctx.state = "REPAIR_OR_RETRIEVE";
        } else this.degrade(ctx, "独立审查在一次修订后仍未通过", ctx.answer);
        return;
      }
      case "REPAIR_OR_RETRIEVE":
        await this.repairOrRetrieve(ctx);
        return;
      case "FINALIZE":
        return;
    }
  }

  private async planRetrieval(ctx: WorkflowContext): Promise<RetrievalPlan> {
    if (!this.llm.isConfigured) return this.fallbackPlan(ctx.fallbackAnalysis, true);
    try {
      const raw = await this.callLlm(ctx, this.prompts.getPlannerPrompt(), [
        "<dynamic_context>", "mode: PLAN", `current_date: ${new Date().toISOString().slice(0, 10)}`,
        `user_query: ${ctx.query}`, "remaining_retrieval_rounds: 2", "</dynamic_context>",
      ].join("\n"));
      return this.augmentPlanWithRuleFallback(
        retrievalPlanSchema.parse(this.parseJson(raw)),
        ctx.fallbackAnalysis,
      );
    } catch {
      return this.fallbackPlan(ctx.fallbackAnalysis, true);
    }
  }

  private async retrieve(ctx: WorkflowContext) {
    if (ctx.retrievalRounds >= MAX_RETRIEVAL_ROUNDS || !ctx.plan) return;
    ctx.retrievalRounds += 1;
    const roundHits: RetrievalHit[] = [];
    for (const sub of ctx.plan.subQuestions) {
      const result = await this.searchTool.execute({
        queries: sub.queries,
        subQuestion: sub.question,
        subjects: ctx.plan.subjects,
        productTypes: ctx.plan.productTypes,
        timeScope: ctx.plan.timeScope,
        requiredEvidence: sub.requiredEvidence,
        topK: 12,
      });
      if (result.ok) roundHits.push(...result.hits);
      else this.record(ctx, ctx.retrievalRounds === 1 ? "RETRIEVE" : "RETRIEVE_AGAIN", result.error, ctx.retrievalRounds, this.searchTool.name);
    }
    ctx.hits = this.mergeEvidence(ctx.hits, roundHits, 20);
    this.record(ctx, ctx.retrievalRounds === 1 ? "RETRIEVE" : "RETRIEVE_AGAIN", `工具返回并去重后 ${ctx.hits.length} 条最终证据`, ctx.retrievalRounds, this.searchTool.name);
  }

  private async assessEvidence(ctx: WorkflowContext): Promise<EvidenceAssessment> {
    if (!ctx.hits.length) return this.fallbackAssessment(ctx, "混合检索未返回证据");
    if (!this.llm.isConfigured) return this.fallbackAssessment(ctx, "未配置模型，不声称已完成证据充分性判断");
    try {
      const raw = await this.callLlm(ctx, this.prompts.getPlannerPrompt(), [
        "<dynamic_context>", "mode: ASSESS", `user_query: ${ctx.query}`,
        `retrieval_round: ${ctx.retrievalRounds}`,
        `remaining_retrieval_rounds: ${MAX_RETRIEVAL_ROUNDS - ctx.retrievalRounds}`,
        `used_queries: ${JSON.stringify(ctx.plan?.subQuestions.flatMap((sub) => sub.queries) ?? [])}`,
        "<evidence_context>", this.contextBuilder.build(ctx.hits), "</evidence_context>", "</dynamic_context>",
      ].join("\n"));
      return this.applyEvidenceSafety(
        evidenceAssessmentSchema.parse(this.parseJson(raw)),
        ctx,
      );
    } catch {
      return this.applyEvidenceSafety(
        this.fallbackAssessment(ctx, "证据判断模型输出无效，安全降级为证据不足"),
        ctx,
      );
    }
  }

  private async generateAnswer(ctx: WorkflowContext): Promise<ComplianceAnswer> {
    const repair = ctx.repairRequest && ctx.repairCount > 0
      ? this.buildRepairContext(ctx)
      : [];
    const raw = await this.callLlm(ctx, this.prompts.getAnswerPrompt(), [
      "<dynamic_context>", `user_query: ${ctx.query}`,
      `evidence_assessment: ${JSON.stringify(ctx.assessment)}`,
      `current_date: ${new Date().toISOString().slice(0, 10)}`,
      ...repair,
      "<evidence_context>", this.contextBuilder.build(ctx.hits, { includeQuoteCandidates: true }), "</evidence_context>", "</dynamic_context>",
    ].join("\n"));
    const modelAnswer = modelAnswerSchema.parse(this.parseJson(raw));
    const label = modelAnswer.directAnswer === "不能确认" ? "需人工合规复核"
      : modelAnswer.directAnswer === "否" ? "不可做"
      : modelAnswer.scope.conditions.length ? "有条件可做" : "可做";
    return {
      directAnswer: modelAnswer.directAnswer,
      conclusionLevel: modelAnswer.conclusionLevel,
      conclusion: this.stripDecision(modelAnswer.conclusion, modelAnswer.directAnswer),
      conclusionLabel: label,
      scope: modelAnswer.scope,
      productStructure: this.structureFromScope(modelAnswer.scope, ctx.analysis),
      regulatoryBasis: modelAnswer.regulatoryBasis.map((basis) => ({
        evidenceId: basis.evidenceId, title: "", publisher: "", url: "", articleNo: "",
        excerpt: basis.quoteExact, quoteExact: basis.quoteExact,
        requirement: basis.supports, status: "",
      })),
      restrictions: modelAnswer.restrictions,
      missingInfo: modelAnswer.missingInfo,
      manualReviewNote: modelAnswer.manualReviewNote,
      confidenceScore: modelAnswer.confidence,
      confidenceReason: modelAnswer.directAnswer === "不能确认"
        ? "现有证据只能支持已明示的一般条件或局部路径，不足以支持确定性许可或禁止结论。"
        : (ctx.assessment?.reasonSummary || ""),
    };
  }

  private buildRepairContext(ctx: WorkflowContext): string[] {
    const request = ctx.repairRequest!;
    const issueText = request.instructions.join("\n");
    const failedIds = [...new Set([...issueText.matchAll(/chunk_[a-z0-9]+/g)].map((match) => match[0]))];
    const exactSources = failedIds.flatMap((id) => {
      const hit = ctx.hits.find((item) => item.id === id);
      return hit ? [`evidenceId: ${id}\nexact_raw_chunk_start\n${hit.text}\nexact_raw_chunk_end`] : [];
    });
    const mandatory = /收益凭证通用发行规则未直接列明雪球结构/.test(issueText)
      ? [
          "mandatory_direct_answer: 不能确认",
          "mandatory_conclusion_level: 证据不足",
          "mandatory_explanation: 必须明确说明现有通用规则未直接列明或许可雪球结构，不得由一般条件推导明确可以。",
          "mandatory_scope_rule: 《私募证券投资基金运作指引》规范投资者侧，不能作为证券公司发行雪球收益凭证的许可依据。修订时应从 regulatoryBasis 删除该文件；如必须提及，只能说明投资规则曾提到该类产品，不能推导发行许可。",
        ]
      : [];
    const crossRegimeMandatory = /不得将私募证券投资基金的‘同一资产’口径跨制度套用/.test(issueText)
      ? [
          "mandatory_cross_regime_rule: 删除集合资产管理计划或私募资管计划的雪球 25% 结论及其相关依据。只保留《私募证券投资基金运作指引》对私募证券投资基金的明确 25% 规则与例外；其他私募产品类型应列为尚不能确认的范围。",
        ]
      : [];
    return [
      `previous_answer: ${JSON.stringify(ctx.draft)}`,
      `repair_source: ${request.source}`,
      `repair_instructions: ${JSON.stringify(request.instructions)}`,
      ...mandatory,
      ...crossRegimeMandatory,
      "repair_rule_1: 只使用同一批证据，不得补造法规或引文。",
      "repair_rule_2: quoteExact 必须从 exact_raw_chunk_start 与 exact_raw_chunk_end 之间逐字连续复制；不能确保时必须删除该 regulatoryBasis，不得改写。",
      ...(exactSources.length ? ["<exact_copy_sources>", ...exactSources, "</exact_copy_sources>"] : []),
    ];
  }

  private async reviewAnswer(ctx: WorkflowContext): Promise<AnswerReview> {
    try {
      const raw = await this.callLlm(ctx, this.prompts.getReviewerPrompt(), [
        "<dynamic_context>", `user_query: ${ctx.query}`,
        `candidate_answer: ${JSON.stringify(ctx.answer)}`,
        `deterministic_validation: ${JSON.stringify(ctx.answer?.citationValidation)}`,
        "<evidence_context>", this.contextBuilder.build(ctx.hits, { includeQuoteCandidates: true }), "</evidence_context>", "</dynamic_context>",
      ].join("\n"));
      return answerReviewValidationSchema.parse(this.parseJson(raw));
    } catch (error) {
      return {
        verdict: "REPAIR",
        issues: [{
          type: "REVIEW_MODEL_ERROR", severity: "CRITICAL", statement: "独立审查未完成", evidenceId: "",
          reason: error instanceof Error ? error.message : "审查模型输出无效", action: "降级为不能确认",
        }],
        repairInstructions: ["独立审查无法验证证据支持关系"], missingEvidence: [], followUpQueries: [],
      };
    }
  }

  private async repairOrRetrieve(ctx: WorkflowContext) {
    const request = ctx.repairRequest;
    if (!request || ctx.repairCount >= MAX_REPAIRS) { this.degrade(ctx, "修订上限已达到", ctx.answer ?? undefined); return; }
    ctx.repairCount += 1;
    this.record(ctx, "REPAIR_OR_RETRIEVE", request.retrieve ? "审查要求补充检索后重新生成一次" : "使用同一批证据修订一次");
    if (request.retrieve) {
      if (ctx.retrievalRounds >= MAX_RETRIEVAL_ROUNDS) { this.degrade(ctx, "审查要求新证据，但两轮检索已用完", ctx.answer ?? undefined); return; }
      const queries = ctx.review?.followUpQueries?.length ? ctx.review.followUpQueries : ctx.assessment?.followUpQueries ?? [];
      if (!queries.length) { this.degrade(ctx, "审查要求检索，但未提供可执行查询", ctx.answer ?? undefined); return; }
      ctx.plan = this.followUpPlan(ctx.plan!, {
        ...(ctx.assessment ?? this.fallbackAssessment(ctx, "审查证据缺口")),
        followUpQueries: queries,
        missingEvidenceTypes: ctx.review?.missingEvidence ?? [],
      });
      ctx.state = "RETRIEVE_AGAIN";
      return;
    }
    ctx.state = "DRAFT_ANSWER";
  }

  private fallbackPlan(analysis: QueryAnalysis, fallbackUsed: boolean): RetrievalPlan {
    return {
      normalizedQuery: analysis.normalizedQuery,
      legalIssue: analysis.legalIssue,
      subjects: analysis.subjects,
      productTypes: analysis.productTypes,
      counterparties: [], timeScope: analysis.timeRange, ambiguities: [],
      subQuestions: analysis.subQuestions.slice(0, 3).map((question, index) => ({
        id: `sq${index + 1}`, question,
        queries: [...new Set([question, analysis.keywords.join(" "), ...analysis.semanticQueries])].filter(Boolean).slice(0, 8),
        formalTerms: analysis.keywords.slice(0, 16), requiredEvidence: analysis.topics.length ? analysis.topics : ["直接规定"],
      })),
      reasonSummary: "规划模型不可用或输出无效，使用受控同义词和基础规则降级",
      fallbackUsed,
    };
  }

  private augmentPlanWithRuleFallback(plan: RetrievalPlan, fallback: QueryAnalysis): RetrievalPlan {
    const safetyQueries = [
      ...fallback.semanticQueries,
      fallback.keywords.filter((term) => term.length >= 4).join(" "),
    ].filter(Boolean).slice(0, 2);
    return {
      ...plan,
      subQuestions: plan.subQuestions.map((sub, index) => index === 0 ? {
        ...sub,
        queries: [...new Set([...sub.queries, ...safetyQueries])].slice(0, 8),
        formalTerms: [...new Set([...sub.formalTerms, ...fallback.keywords])].slice(0, 16),
      } : sub),
    };
  }

  private fallbackAssessment(ctx: WorkflowContext, reason: string): EvidenceAssessment {
    return {
      sufficient: false, answerability: "UNCERTAIN", evidenceLevel: "INSUFFICIENT",
      supportedSubQuestions: [], missingSubQuestions: ctx.plan?.subQuestions.map((sub) => sub.question) ?? [],
      missingEvidenceTypes: ctx.plan?.subQuestions.flatMap((sub) => sub.requiredEvidence) ?? [],
      followUpQueries: ctx.retrievalRounds < MAX_RETRIEVAL_ROUNDS
        ? (ctx.plan?.subQuestions.flatMap((sub) => sub.queries).slice(0, 8) ?? []) : [],
      reasonSummary: reason,
    };
  }

  private applyEvidenceSafety(assessment: EvidenceAssessment, ctx: WorkflowContext): EvidenceAssessment {
    const asksOwnUnderlying = /(自己|自身|本身|本公司).{0,10}(标的|股票)/.test(ctx.query);
    if (!asksOwnUnderlying) return assessment;
    const currentCounterpartyLimits = ctx.hits.filter((hit) =>
      /(?:期货)?风险管理公司不得与上市公司|证券公司不得违规与上市公司/.test(hit.text.replace(/\s+/g, ""))
    );
    const futureGeneralBan = ctx.hits.find((hit) =>
      /尚未施行|未生效/.test(hit.status)
      && /上市公司.*不得达成.*其发行的股票/.test(hit.text.replace(/\s+/g, ""))
    );
    if (!currentCounterpartyLimits.length || !futureGeneralBan) return assessment;
    return {
      sufficient: true,
      answerability: "NO",
      evidenceLevel: "DIRECT",
      supportedSubQuestions: ["现行交易对手限制", "已公布尚未施行的未来一般禁止"],
      missingSubQuestions: ["其他现行交易对手路径是否可行"],
      missingEvidenceTypes: ["其他现行交对手的直接规则"],
      followUpQueries: [],
      reasonSummary: "对未限定范围的‘可以吗’，不能笼统认定可以：现行证据已明确禁止证券公司或期货风险管理公司等重要交易对手路径，但不得据此声称所有现行交易对手均被禁止；已公布尚未施行的未来规则则将从上市公司端一般性禁止此类交易。",
    };
  }

  private followUpPlan(plan: RetrievalPlan, assessment: EvidenceAssessment): RetrievalPlan {
    return {
      ...plan,
      subQuestions: [{
        id: "follow_up",
        question: assessment.missingSubQuestions.join("；") || plan.legalIssue,
        queries: [...new Set(assessment.followUpQueries)].slice(0, 8),
        formalTerms: [],
        requiredEvidence: assessment.missingEvidenceTypes.length ? assessment.missingEvidenceTypes : ["补充直接规定、例外和效力条件"],
      }],
      reasonSummary: `第二轮针对证据缺口: ${assessment.reasonSummary}`,
    };
  }

  private analysisFromPlan(base: QueryAnalysis, plan: RetrievalPlan): QueryAnalysis {
    return {
      ...base,
      normalizedQuery: plan.normalizedQuery,
      legalIssue: plan.legalIssue,
      subjects: [...new Set([...plan.subjects, ...base.subjects])],
      productTypes: [...new Set([...plan.productTypes, ...base.productTypes])],
      timeRange: plan.timeScope || base.timeRange,
      subQuestions: plan.subQuestions.map((sub) => sub.question),
      keywords: [...new Set([...plan.subQuestions.flatMap((sub) => [...sub.formalTerms, ...sub.queries]), ...base.keywords])].slice(0, 40),
      semanticQueries: [...new Set(plan.subQuestions.flatMap((sub) => sub.queries))],
    };
  }

  private mergeEvidence(existing: RetrievalHit[], incoming: RetrievalHit[], limit: number) {
    const merged = new Map<string, RetrievalHit>();
    for (const hit of [...existing, ...incoming]) {
      const current = merged.get(hit.id);
      if (!current || hit.score > current.score) merged.set(hit.id, hit);
      else if (hit.subQuestion && !current.subQuestion.includes(hit.subQuestion)) current.subQuestion = `${current.subQuestion}；${hit.subQuestion}`;
    }
    return [...merged.values()]
      .sort((a, b) => Number(a.isSupplementalContext) - Number(b.isSupplementalContext) || b.score - a.score)
      .slice(0, limit);
  }

  /**
   * The model may collapse line breaks or full-width ASCII punctuation.  Snap
   * only a format-normalized exact match back to a continuous raw Chunk span.
   * Changed words, numbers, dates, percentages and terms never match.
   */
  private snapQuotesToOriginal(answer: ComplianceAnswer, hits: RetrievalHit[]): ComplianceAnswer {
    const evidence = new Map(hits.map((hit) => [hit.id, hit.text]));
    return {
      ...answer,
      regulatoryBasis: answer.regulatoryBasis.map((basis) => {
        const text = evidence.get(basis.evidenceId);
        const quote = basis.quoteExact || basis.excerpt;
        if (!text || !quote || text.includes(quote)) return basis;
        const snapped = this.findRawSpan(text, quote);
        return snapped ? { ...basis, quoteExact: snapped, excerpt: snapped } : basis;
      }),
    };
  }

  private findRawSpan(raw: string, candidate: string): string | null {
    const normalize = (value: string, withMap: boolean) => {
      let normalized = "";
      const starts: number[] = [];
      const ends: number[] = [];
      for (let offset = 0; offset < value.length;) {
        const codePoint = value.codePointAt(offset)!;
        const char = String.fromCodePoint(codePoint);
        const end = offset + char.length;
        for (const normalizedChar of char.normalize("NFKC")) {
          if (/\s/u.test(normalizedChar)) continue;
          normalized += normalizedChar;
          if (withMap) { starts.push(offset); ends.push(end); }
        }
        offset = end;
      }
      return { normalized, starts, ends };
    };
    const source = normalize(raw, true);
    const target = normalize(candidate, false).normalized;
    if (!target) return null;
    const index = source.normalized.indexOf(target);
    if (index < 0) return null;
    return raw.slice(source.starts[index], source.ends[index + target.length - 1]);
  }

  private structureFromScope(scope: z.infer<typeof modelAnswerSchema>["scope"], analysis: QueryAnalysis) {
    return {
      underlyingAsset: /(股票|股票指数|债券|利率|外汇)/.exec(analysis.normalizedQuery)?.[1] || "",
      productType: scope.product || analysis.productTypes.join("、"),
      transactionStructure: analysis.normalizedQuery.includes("雪球") ? "雪球/敲入敲出/自动赎回结构" : "",
      counterparty: scope.counterparty,
      investorType: scope.subject,
      isCrossBorder: /跨境|境外|外汇/.test(analysis.normalizedQuery),
      riskPoints: analysis.topics.filter((value) => /风控|适当性|禁止|披露|比例/.test(value)),
      missingInfo: [],
    };
  }

  private insufficientAnswer(analysis: QueryAnalysis, hits: RetrievalHit[], reason: string): ComplianceAnswer {
    return {
      directAnswer: "不能确认", conclusionLevel: "证据不足",
      conclusion: "根据当前知识库检索结果，暂时无法形成确定结论。",
      conclusionLabel: "需人工合规复核",
      scope: { subject: analysis.subjects.join("、"), product: analysis.productTypes.join("、"), counterparty: "", time: analysis.timeRange, conditions: [] },
      productStructure: this.structureFromScope({ subject: analysis.subjects.join("、"), product: analysis.productTypes.join("、"), counterparty: "", time: analysis.timeRange, conditions: [] }, analysis),
      regulatoryBasis: [], restrictions: [], missingInfo: [reason],
      manualReviewNote: "当前未完成可以支持确定性结论的规划、验证和独立审查。",
      confidenceScore: "low", confidenceReason: reason,
      citationValidation: { passed: false, issues: [reason] },
      reviewValidation: { passed: false, verdict: "SKIPPED" },
      retrievalTrace: { chunkHits: hits.length, documentHits: new Set(hits.map((hit) => hit.documentId)).size, strategy: "controlled-agent + hybrid_regulation_search" },
    };
  }

  private degrade(ctx: WorkflowContext, reason: string, base?: ComplianceAnswer) {
    ctx.degraded = true; ctx.degradationReason = reason;
    ctx.answer = {
      ...(base ?? this.insufficientAnswer(ctx.analysis, ctx.hits, reason)),
      directAnswer: "不能确认", conclusionLevel: "证据不足",
      conclusion: "根据当前知识库检索结果，暂时无法形成确定结论。",
      conclusionLabel: "需人工合规复核",
      missingInfo: [...new Set([...(base?.missingInfo ?? []), reason])],
      manualReviewNote: "受控智能体已达到检索、修订或审查上限，需要人工合规复核。",
      confidenceScore: "low", confidenceReason: reason,
      reviewValidation: { passed: false, verdict: ctx.review?.verdict ?? "SKIPPED" },
    };
    this.record(ctx, "FINALIZE", `降级: ${reason}`);
    ctx.state = "FINALIZE";
  }

  private async callLlm(ctx: WorkflowContext, system: string, user: string) {
    ctx.llmCalls += 1;
    return this.llm.chat(system, user, 120000);
  }

  private parseJson(raw: string): unknown {
    const cleaned = raw.replace(/```(?:json)?/gi, "").replace(/```/g, "").trim();
    const start = cleaned.indexOf("{"); const end = cleaned.lastIndexOf("}");
    if (start < 0 || end < start) throw new Error("模型未返回合法 JSON 对象");
    return JSON.parse(cleaned.slice(start, end + 1));
  }

  private stripDecision(conclusion: string, decision: string) {
    return conclusion.replace(new RegExp(`^${decision}[，,。；;：:\\s]+`), "").trim();
  }

  private record(ctx: WorkflowContext, state: AgentState, summary: string, round?: number, toolName?: string) {
    ctx.trace.push({ state, summary: summary.slice(0, 500), ...(round ? { round } : {}), ...(toolName ? { toolName } : {}) });
  }
}
