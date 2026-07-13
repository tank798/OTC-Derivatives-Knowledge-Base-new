import { Injectable } from "@nestjs/common";
import { randomUUID } from "node:crypto";
import { z } from "zod";
import type { PromptKey } from "@otc/prompts";
import {
  agentAnswerDraftSchema,
  type AgentProgressEvent,
  type AgentChatResponse,
  type RetrievalHit,
} from "@otc/shared";
import { CitationValidatorService } from "../citation-validator/citation-validator.service";
import { ContextBuilderService } from "../context-builder/context-builder.service";
import { LlmService, type LlmChatMessage } from "../llm/llm.service";
import { PromptService } from "../prompt/prompt.service";
import { AgentRunLoggerService } from "./agent-run-logger.service";
import { HybridRegulationSearchTool } from "./hybrid-regulation-search.tool";

const MAX_SEARCHES = 2;
const MAX_ACTIVE_CHUNKS = 10;
const MAX_CITATION_REPAIRS = 1;
const MAX_ARGUMENT_REPAIRS_PER_TURN = 1;
const MAX_ACTIONS_PER_TURN = 8;
const SESSION_TTL_MS = 2 * 60 * 60 * 1000;

const rewrittenQuestionSchema = z.object({
  rewrittenQuery: z.string().min(1),
});

const askUserSchema = z.object({
  message: z.string().min(1),
});

const searchSchema = z.object({
  query: z.string().min(1),
  purpose: z.string().min(1),
  retainEvidenceIds: z.array(z.string()).default([]),
});

type ToolDefinition = {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
};

type ProgressCallback = (event: AgentProgressEvent) => void;
type RunOptions = { sessionId?: string; debug?: boolean; onProgress?: ProgressCallback };

type CompletedExchange = {
  question: string;
  searchedQuery: string;
  answerSummary: string;
};

interface AgentSession {
  id: string;
  runId: string;
  messages: LlmChatMessage[];
  currentQuestion: string;
  completed: boolean;
  history: CompletedExchange[];
  proposedQuery: string;
  rewritePresented: boolean;
  userRespondedToRewrite: boolean;
  searchCount: number;
  repairCount: number;
  llmCalls: number;
  searchedQueries: string[];
  allHits: RetrievalHit[];
  activeHits: RetrievalHit[];
  searchToolCallIds: string[];
  createdAt: number;
  lastUsedAt: number;
  argumentRepairsThisTurn: number;
}

const TOOLS: ToolDefinition[] = [
  {
    type: "function",
    function: {
      name: "present_rewritten_question",
      description: "展示对用户问题的法规检索式改写，并等待用户确认。新问题的第一步必须使用此工具。",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["rewrittenQuery"],
        properties: {
          rewrittenQuery: {
            type: "string",
            description: "保持原意，但主体、产品、行为和法规问题更清楚的一个完整问题。",
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "ask_user",
      description: "当用户否定了改写但没有给出正确问法，或确实无法理解其意图时，继续向用户追问。",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["message"],
        properties: {
          message: { type: "string", description: "简洁、自然的追问。" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "hybrid_regulation_search",
      description: "对一个完整的法规问题执行 BM25 + 向量 + RRF 混合检索。整个回答最多调用两次。",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["query", "purpose", "retainEvidenceIds"],
        properties: {
          query: {
            type: "string",
            description: "唯一、自然、完整的中文问句；不得是子问题数组或关键词堆砌。",
          },
          purpose: { type: "string", description: "本轮要找什么；第二轮时说明第一轮还缺少的关键证据。" },
          retainEvidenceIds: {
            type: "array",
            items: { type: "string" },
            description: "第一轮传空数组；第二轮列出第一轮中仍相关、必须保留的 evidenceId。",
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "submit_regulatory_answer",
      description: "提交最终法规回答。程序只校验 evidenceId 和逐字引文是否真实，然后回填法规元数据。",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["conclusion", "reasoningSummary", "regulatoryBasis"],
        properties: {
          conclusion: { type: "string", description: "先说的直接结论；证据不足时明确说无法得出确定结论。" },
          reasoningSummary: {
            type: "string",
            description: "通常400至800字、3至6个详细分析段落，以两个换行符分隔；不写标题，不重复结论，不暴露隐藏思维过程。",
          },
          regulatoryBasis: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              required: ["evidenceId", "quoteExact", "explanation"],
              properties: {
                evidenceId: { type: "string" },
                quoteExact: { type: "string", description: "来自对应 Chunk 的连续逐字原文。" },
                explanation: { type: "string", description: "该原文规定了什么，以及它对用户问题的作用边界。" },
              },
            },
          },
          missingInformation: { type: "array", items: { type: "string" } },
          manualReviewNote: { type: "string" },
        },
      },
    },
  },
];

const TOOLS_BY_PROMPT_STAGE: Record<PromptKey, string[]> = {
  questionRewrite: ["present_rewritten_question", "ask_user"],
  retrieval: ["hybrid_regulation_search", "ask_user"],
  evidenceAnswer: ["hybrid_regulation_search", "submit_regulatory_answer"],
  citationRepair: ["submit_regulatory_answer"],
};

@Injectable()
export class RegulatoryAgentService {
  private readonly sessions = new Map<string, AgentSession>();

  constructor(
    private readonly llm: LlmService,
    private readonly prompts: PromptService,
    private readonly searchTool: HybridRegulationSearchTool,
    private readonly contextBuilder: ContextBuilderService,
    private readonly validator: CitationValidatorService,
    private readonly logger: AgentRunLoggerService,
  ) {}

  async run(message: string, options: RunOptions = {}): Promise<AgentChatResponse> {
    if (!this.llm.isConfigured) throw new Error("未配置 LLM_API_KEY，无法启动对话式法规 Agent");
    this.removeExpiredSessions();
    const session = this.getOrCreateSession(options.sessionId);
    if (session.completed) this.prepareForNextQuestion(session);
    session.lastUsedAt = Date.now();
    session.argumentRepairsThisTurn = 0;
    if (!session.currentQuestion) session.currentQuestion = message;
    if (session.rewritePresented) session.userRespondedToRewrite = true;
    session.messages.push({ role: "user", content: message });
    this.logger.write(session.runId, session.id, "user_message", { message });

    for (let action = 0; action < MAX_ACTIONS_PER_TURN; action += 1) {
      const promptStage = this.promptStage(session);
      const availableTools = this.toolsForPromptStage(promptStage);
      const modelTier = this.modelTier(promptStage);
      const llmStepId = `agent-${session.llmCalls + 1}`;
      const llmStepLabel = this.llmStepLabel(promptStage);
      options.onProgress?.({ id: llmStepId, label: llmStepLabel, status: "running" });
      const startedAt = Date.now();
      let completion: Awaited<ReturnType<LlmService["chatWithTools"]>>;
      try {
        completion = await this.llm.chatWithTools(
          this.runtimePrompt(session, promptStage),
          session.messages,
          availableTools,
          150_000,
          { tier: modelTier, thinking: modelTier === "fast" ? "disabled" : undefined },
        );
      } catch (error) {
        this.logger.write(session.runId, session.id, "agent_action_failed", {
          attemptedCall: session.llmCalls + 1,
          promptStage,
          promptFile: this.prompts.getAgentPromptPath(promptStage),
          modelTier,
          model: modelTier === "fast" ? this.llm.fastModelName : this.llm.modelName,
          availableTools: availableTools.map((tool) => tool.function.name),
          latencyMs: Date.now() - startedAt,
          error: error instanceof Error ? error.message : "未知模型调用错误",
        });
        throw error;
      }
      session.llmCalls += 1;
      options.onProgress?.({
        id: llmStepId,
        label: this.completedLabel(llmStepLabel),
        status: "done",
        detail: this.formatDuration(Date.now() - startedAt),
      });
      this.logger.write(session.runId, session.id, "agent_action", {
        llmCall: session.llmCalls,
        promptStage,
        promptFile: this.prompts.getAgentPromptPath(promptStage),
        latencyMs: Date.now() - startedAt,
        content: completion.content ?? "",
        modelTier,
        model: modelTier === "fast" ? this.llm.fastModelName : this.llm.modelName,
        availableTools: availableTools.map((tool) => tool.function.name),
        toolNames: completion.toolCalls.map((call) => call.name),
        finishReason: completion.finishReason,
        selectedToolArgumentKeys: completion.toolCalls[0]
          ? Object.keys(completion.toolCalls[0].arguments)
          : [],
        toolArgumentParseError: completion.toolCalls[0]?.argumentParseError ?? "",
        toolArgumentJsonRepaired: completion.toolCalls[0]?.argumentJsonRepaired ?? false,
      });

      const selectedCall = completion.toolCalls[0];
      if (!selectedCall) {
        const content = completion.content?.trim();
        if (!content) throw new Error("Agent 未返回可执行动作");
        session.messages.push({ role: "assistant", content });
        this.logger.write(session.runId, session.id, "agent_plain_message", { content });
        return this.response(session, "awaiting_clarification", content, options.debug);
      }

      session.messages.push({
        role: "assistant",
        content: completion.content,
        tool_calls: [{
          id: selectedCall.id,
          type: "function",
          function: { name: selectedCall.name, arguments: JSON.stringify(selectedCall.arguments) },
        }],
      });

      const terminal = await this.executeTool(session, selectedCall, Boolean(options.debug), options.onProgress);
      if (terminal) return terminal;
    }

    throw new Error(`Agent 在 ${MAX_ACTIONS_PER_TURN} 次有界动作内未完成当前回合，请重新发起问题`);
  }

  private async executeTool(
    session: AgentSession,
    call: { id: string; name: string; arguments: Record<string, unknown>; argumentParseError?: string },
    debug: boolean,
    onProgress?: ProgressCallback,
  ): Promise<AgentChatResponse | null> {
    switch (call.name) {
      case "present_rewritten_question": {
        const parsed = rewrittenQuestionSchema.safeParse(call.arguments);
        if (!parsed.success) return this.rejectToolArguments(session, call.id, call.name, parsed.error.message);
        session.proposedQuery = parsed.data.rewrittenQuery.trim();
        session.rewritePresented = true;
        session.userRespondedToRewrite = false;
        const visibleMessage = [
          `我将你的问题理解为：“${session.proposedQuery}”`,
          "",
          "这是你想问的问题吗？如果不是，请直接告诉我正确的问法。",
        ].join("\n");
        this.addToolResult(session, call.id, {
          status: "shown_to_user",
          rewrittenQuery: session.proposedQuery,
          instruction: "等待用户确认、否定或给出修正后的问题。",
        });
        this.logger.write(session.runId, session.id, "rewritten_question", {
          rewrittenQuery: session.proposedQuery,
        });
        return this.response(session, "awaiting_confirmation", visibleMessage, debug);
      }

      case "ask_user": {
        const parsed = askUserSchema.safeParse(call.arguments);
        if (!parsed.success) return this.rejectToolArguments(session, call.id, call.name, parsed.error.message);
        this.addToolResult(session, call.id, { status: "shown_to_user", message: parsed.data.message });
        this.logger.write(session.runId, session.id, "clarification_requested", { message: parsed.data.message });
        return this.response(session, "awaiting_clarification", parsed.data.message, debug);
      }

      case "hybrid_regulation_search": {
        const parsed = searchSchema.safeParse(call.arguments);
        if (!parsed.success) return this.rejectToolArguments(session, call.id, call.name, parsed.error.message);
        if (!session.rewritePresented || !session.userRespondedToRewrite) {
          this.addToolResult(session, call.id, {
            status: "rejected",
            error: "用户尚未看到或回复改写后的问题。请先调用 present_rewritten_question，并等待用户下一轮回复。",
          });
          return null;
        }
        if (session.searchCount >= MAX_SEARCHES) {
          this.addToolResult(session, call.id, {
            status: "rejected",
            error: "已达到两轮检索上限。请根据当前证据提交回答，证据不足时如实说明。",
          });
          return null;
        }
        return this.executeSearch(session, call.id, parsed.data, onProgress);
      }

      case "submit_regulatory_answer": {
        const parsed = agentAnswerDraftSchema.safeParse(call.arguments);
        if (!parsed.success) {
          return this.rejectToolArguments(
            session,
            call.id,
            call.name,
            call.argumentParseError || parsed.error.issues.map((issue) => `${issue.path.join(".") || "root"}: ${issue.message}`).join("；"),
          );
        }
        const validationId = `citation-${session.repairCount + 1}`;
        onProgress?.({ id: validationId, label: "正在校验法规引用真实性", status: "running" });
        const validation = this.validator.validateDraft(parsed.data, session.activeHits);
        onProgress?.({
          id: validationId,
          label: validation.issues.length ? "引用校验发现问题" : "法规引用校验通过",
          status: "done",
          detail: validation.issues.length ? `${validation.issues.length} 项待修正` : undefined,
        });
        if (validation.issues.length && session.repairCount < MAX_CITATION_REPAIRS) {
          session.repairCount += 1;
          this.addToolResult(session, call.id, {
            status: "citation_validation_failed",
            issues: validation.issues,
            instruction: "只修正 evidenceId 或 quoteExact 的真实性错误，然后再调用一次 submit_regulatory_answer。不要改强法律结论。",
          });
          this.logger.write(session.runId, session.id, "citation_validation_failed", {
            repairCount: session.repairCount,
            issues: validation.issues,
          });
          return null;
        }

        if (validation.issues.length) {
          this.logger.write(session.runId, session.id, "citation_validation_terminal_failure", {
            issues: validation.issues,
            searchCount: session.searchCount,
            repairCount: session.repairCount,
            llmCalls: session.llmCalls,
          });
          throw new Error(
            `引用真实性修订后仍未通过，系统已停止输出本次回答。${validation.issues.join("；")}`,
          );
        }

        const answer = validation.answer;

        this.addToolResult(session, call.id, {
          status: "completed",
          citationValidation: answer.citationValidation,
        });
        session.completed = true;
        session.history.push({
          question: session.currentQuestion,
          searchedQuery: session.searchedQueries[0] || session.proposedQuery || session.currentQuestion,
          answerSummary: [answer.conclusion, answer.reasoningSummary].filter(Boolean).join("\n"),
        });
        session.history = session.history.slice(-8);
        this.logger.write(session.runId, session.id, "final_answer", {
          conclusion: answer.conclusion,
          reasoningSummary: answer.reasoningSummary,
          regulatoryBasis: answer.regulatoryBasis.map((basis) => ({
            evidenceId: basis.evidenceId,
            title: basis.title,
            articleNo: basis.articleNo,
            quoteExact: basis.quoteExact,
            explanation: basis.explanation,
            url: basis.url,
          })),
          missingInformation: answer.missingInformation,
          manualReviewNote: answer.manualReviewNote,
          citationValidationPassed: answer.citationValidation.passed,
          citationIssues: answer.citationValidation.issues,
          citedEvidenceIds: answer.regulatoryBasis.map((basis) => basis.evidenceId),
          searchCount: session.searchCount,
          repairCount: session.repairCount,
          llmCalls: session.llmCalls,
        });
        return this.response(session, "complete", answer.conclusion, debug, answer);
      }

      default:
        this.addToolResult(session, call.id, {
          status: "rejected",
          error: `未知工具: ${call.name}`,
        });
        return null;
    }
  }

  private async executeSearch(
    session: AgentSession,
    toolCallId: string,
    input: z.infer<typeof searchSchema>,
    onProgress?: ProgressCallback,
  ): Promise<null> {
    const round = session.searchCount + 1;
    const startedAt = Date.now();
    const searchId = `round-${round}-search`;
    onProgress?.({ id: searchId, label: `正在检索法规（第 ${round} 轮）`, status: "running" });
    const result = await this.searchTool.execute({
      queries: [input.query.trim()],
      subQuestion: input.query.trim(),
      subjects: [],
      productTypes: [],
      counterparties: [],
      timeScope: "",
      requiredEvidence: [],
      topK: MAX_ACTIVE_CHUNKS,
    }, (event) => onProgress?.({ ...event, id: `round-${round}-${event.id}` }));

    if (!result.ok) {
      onProgress?.({ id: searchId, label: `第 ${round} 轮法规检索失败`, status: "done" });
      this.addToolResult(session, toolCallId, { status: "search_failed", error: result.error });
      this.logger.write(session.runId, session.id, "search_failed", {
        round,
        query: input.query,
        error: result.error,
        latencyMs: Date.now() - startedAt,
      });
      return null;
    }

    session.searchCount = round;
    session.searchedQueries.push(input.query.trim());
    session.allHits = this.mergeHits(session.allHits, result.hits);

    if (round === 1) {
      session.activeHits = result.hits.slice(0, MAX_ACTIVE_CHUNKS);
    } else {
      const retainedIds = new Set(input.retainEvidenceIds);
      const retained = session.activeHits.filter((hit) => retainedIds.has(hit.id));
      session.activeHits = this.mergeHits(retained, result.hits).slice(0, MAX_ACTIVE_CHUNKS);
      this.compactPreviousSearchResults(session, retained.map((hit) => hit.id));
    }

    session.searchToolCallIds.push(toolCallId);
    onProgress?.({
      id: searchId,
      label: `第 ${round} 轮法规检索完成`,
      status: "done",
      detail: `保留 ${session.activeHits.length} 个 Chunk`,
    });
    this.addToolResult(session, toolCallId, {
      status: "completed",
      retrievalRound: round,
      purpose: input.purpose,
      searchedQuery: input.query.trim(),
      returnedChunkCount: result.hits.length,
      activeChunkCount: session.activeHits.length,
      activeEvidenceIds: session.activeHits.map((hit) => hit.id),
      instruction: round < MAX_SEARCHES
        ? "请阅读证据并自主判断：若足够就提交回答；若确有关键缺口，可再检索一个更准确的完整问题。"
        : "已达检索上限。请合并利用下列证据提交回答；证据不足时如实说明。",
      evidenceContext: this.contextBuilder.build(session.activeHits, { includeQuoteCandidates: true }),
    });

    this.logger.write(session.runId, session.id, "hybrid_search", {
      round,
      query: input.query.trim(),
      purpose: input.purpose,
      retainedEvidenceIds: input.retainEvidenceIds,
      returnedChunkCount: result.hits.length,
      activeEvidenceIds: session.activeHits.map((hit) => hit.id),
      ranks: result.hits.map((hit) => ({
        evidenceId: hit.id,
        title: hit.title,
        bm25Rank: hit.bm25Rank ?? null,
        vectorRank: hit.vectorRank ?? null,
        rrfRank: hit.rrfRank ?? null,
      })),
      latencyMs: Date.now() - startedAt,
    });
    return null;
  }

  private compactPreviousSearchResults(session: AgentSession, retainedEvidenceIds: string[]) {
    const priorIds = new Set(session.searchToolCallIds);
    session.messages = session.messages.map((message) => {
      if (message.role !== "tool" || !priorIds.has(message.tool_call_id)) return message;
      return {
        ...message,
        content: JSON.stringify({
          status: "superseded_by_combined_context",
          retainedEvidenceIds,
          instruction: "完整原文已合并进最新一轮工具结果，请以最新 active evidence context 为准。",
        }),
      };
    });
  }

  private rejectToolArguments(
    session: AgentSession,
    toolCallId: string,
    toolNameOrDetail: string,
    maybeDetail?: string,
  ): null {
    const toolName = maybeDetail ? toolNameOrDetail : "unknown_tool";
    const detail = maybeDetail ?? toolNameOrDetail;
    session.argumentRepairsThisTurn += 1;
    this.logger.write(session.runId, session.id, "tool_arguments_invalid", {
      toolName,
      repairAttempt: session.argumentRepairsThisTurn,
      detail,
    });
    if (session.argumentRepairsThisTurn > MAX_ARGUMENT_REPAIRS_PER_TURN) {
      throw new Error(`Agent 连续返回无效的 ${toolName} 参数，已停止重复调用。最后错误：${detail}`);
    }
    this.addToolResult(session, toolCallId, {
      status: "invalid_arguments",
      error: detail,
      instruction: "请只修正工具参数格式并重试一次。若再次无效，当前回合会终止，不能继续重复调用。",
    });
    return null;
  }

  private addToolResult(session: AgentSession, toolCallId: string, result: Record<string, unknown>) {
    session.messages.push({ role: "tool", tool_call_id: toolCallId, content: JSON.stringify(result) });
  }

  private mergeHits(existing: RetrievalHit[], incoming: RetrievalHit[]) {
    const merged = new Map(existing.map((hit) => [hit.id, hit]));
    for (const hit of incoming) if (!merged.has(hit.id)) merged.set(hit.id, hit);
    return [...merged.values()];
  }

  private response(
    session: AgentSession,
    stage: AgentChatResponse["stage"],
    message: string,
    debug = false,
    answer?: AgentChatResponse["answer"],
  ): AgentChatResponse {
    return {
      sessionId: session.id,
      stage,
      message,
      ...(session.proposedQuery ? { proposedQuery: session.proposedQuery } : {}),
      ...(answer ? { answer } : {}),
      hits: stage === "complete" ? session.activeHits : [],
      ...(debug ? {
        trace: {
          runId: session.runId,
          searchCount: session.searchCount,
          repairCount: session.repairCount,
          llmCalls: session.llmCalls,
          searchedQueries: session.searchedQueries,
          evidenceIds: session.activeHits.map((hit) => hit.id),
        },
      } : {}),
    };
  }

  private runtimePrompt(session: AgentSession, promptStage: PromptKey) {
    return [
      this.prompts.getAgentPrompt(promptStage),
      "",
      "<runtime_context>",
      `prompt_stage: ${promptStage}`,
      `current_date: ${new Date().toISOString().slice(0, 10)}`,
      `primary_model: ${this.llm.modelName}`,
      `fast_model: ${this.llm.fastModelName}`,
      `searches_used: ${session.searchCount}`,
      `searches_remaining: ${MAX_SEARCHES - session.searchCount}`,
      `citation_repairs_used: ${session.repairCount}`,
      `citation_repairs_remaining: ${MAX_CITATION_REPAIRS - session.repairCount}`,
      `current_active_chunk_count: ${session.activeHits.length}`,
      "</runtime_context>",
    ].join("\n");
  }

  private promptStage(session: AgentSession): PromptKey {
    if (!session.rewritePresented) return "questionRewrite";
    if (session.repairCount > 0) return "citationRepair";
    if (session.searchCount === 0) return "retrieval";
    return "evidenceAnswer";
  }

  private toolsForPromptStage(promptStage: PromptKey) {
    const allowedNames = new Set(TOOLS_BY_PROMPT_STAGE[promptStage]);
    return TOOLS.filter((tool) => allowedNames.has(tool.function.name));
  }

  private modelTier(promptStage: PromptKey): "default" | "fast" {
    return promptStage === "questionRewrite" || promptStage === "citationRepair"
      ? "fast"
      : "default";
  }

  private llmStepLabel(promptStage: PromptKey) {
    if (promptStage === "questionRewrite") return "正在理解并改写问题";
    if (promptStage === "retrieval") return "正在确认问题并准备检索";
    if (promptStage === "citationRepair") return "正在按校验结果修正引用";
    return "正在阅读法规并形成回答";
  }

  private completedLabel(label: string) {
    return label.replace(/^正在/, "已完成");
  }

  private formatDuration(milliseconds: number) {
    const seconds = milliseconds / 1000;
    return `${seconds >= 10 ? seconds.toFixed(1) : seconds.toFixed(2)} s`;
  }

  private prepareForNextQuestion(session: AgentSession) {
    session.messages = session.history.flatMap((exchange) => [
      { role: "user" as const, content: exchange.question },
      {
        role: "assistant" as const,
        content: [
          `上一问题的检索表达：${exchange.searchedQuery}`,
          exchange.answerSummary,
        ].join("\n"),
      },
    ]);
    session.currentQuestion = "";
    session.completed = false;
    session.proposedQuery = "";
    session.rewritePresented = false;
    session.userRespondedToRewrite = false;
    session.searchCount = 0;
    session.repairCount = 0;
    session.searchedQueries = [];
    session.allHits = [];
    session.activeHits = [];
    session.searchToolCallIds = [];
    session.argumentRepairsThisTurn = 0;
    this.logger.write(session.runId, session.id, "next_question_started", {
      preservedHistoryCount: session.history.length,
    });
  }

  private getOrCreateSession(sessionId?: string): AgentSession {
    if (sessionId) {
      const existing = this.sessions.get(sessionId);
      if (!existing) throw new Error("对话已失效，系统将为当前消息建立新的会话");
      return existing;
    }

    const now = Date.now();
    const session: AgentSession = {
      id: randomUUID(),
      runId: `agent-run-${new Date().toISOString().replaceAll(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`,
      messages: [],
      currentQuestion: "",
      completed: false,
      history: [],
      proposedQuery: "",
      rewritePresented: false,
      userRespondedToRewrite: false,
      searchCount: 0,
      repairCount: 0,
      llmCalls: 0,
      searchedQueries: [],
      allHits: [],
      activeHits: [],
      searchToolCallIds: [],
      createdAt: now,
      lastUsedAt: now,
      argumentRepairsThisTurn: 0,
    };
    this.sessions.set(session.id, session);
    this.logger.write(session.runId, session.id, "session_started", {
      model: this.llm.modelName,
      fastModel: this.llm.fastModelName,
      promptFiles: Object.values({
        questionRewrite: this.prompts.getAgentPromptPath("questionRewrite"),
        retrieval: this.prompts.getAgentPromptPath("retrieval"),
        evidenceAnswer: this.prompts.getAgentPromptPath("evidenceAnswer"),
        citationRepair: this.prompts.getAgentPromptPath("citationRepair"),
      }),
      maxSearches: MAX_SEARCHES,
      maxActiveChunks: MAX_ACTIVE_CHUNKS,
      maxCitationRepairs: MAX_CITATION_REPAIRS,
    });
    return session;
  }

  private removeExpiredSessions() {
    const cutoff = Date.now() - SESSION_TTL_MS;
    for (const [id, session] of this.sessions) {
      if (session.lastUsedAt < cutoff) this.sessions.delete(id);
    }
  }
}
