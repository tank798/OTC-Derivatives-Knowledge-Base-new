import { z } from "zod";

// ────────── 检索命中 ──────────
export const retrievalHitSchema = z.object({
  source: z.enum(["evidence", "clause", "document", "chunk"]),
  id: z.string(),
  documentId: z.string().optional().default(""),
  chunkId: z.string().optional().default(""),
  title: z.string(),
  publisher: z.string().optional().default(""),
  url: z.string().optional().default(""),
  publishedAt: z.string().optional().default(""),
  effectiveAt: z.string().optional().default(""),
  articleNo: z.string().optional().default(""),
  articleEnd: z.string().optional().default(""),
  chapterTitle: z.string().optional().default(""),
  documentNumber: z.string().optional().default(""),
  text: z.string(),
  excerpt: z.string().optional().default(""),
  score: z.number(),
  authorityLevel: z.string().optional().default(""),
  status: z.string().optional().default(""),
  verificationStatus: z.string().optional().default(""),
  matchReason: z.string().optional().default(""),
  retrievalMethods: z.array(z.string()).optional().default([]),
  localFilePath: z.string().optional().default(""),
  bm25Rank: z.number().int().positive().nullable().optional(),
  vectorRank: z.number().int().positive().nullable().optional(),
  rrfRank: z.number().int().positive().nullable().optional(),
  documentRank: z.number().int().positive().nullable().optional(),
  isSupplementalContext: z.boolean().optional().default(false),
  subQuestion: z.string().optional().default(""),
});

export type RetrievalHit = z.infer<typeof retrievalHitSchema>;

// ───────── 对话式法规 Agent ─────────
// Agent 只负责改写、检索、判断证据是否足够以及撰写回答。
// 最终法规元数据由程序根据 evidenceId 回填，不让模型自行编造。
export const agentAnswerDraftSchema = z.object({
  conclusion: z.string().min(1),
  reasoningSummary: z.string().min(1),
  regulatoryBasis: z.array(z.object({
    evidenceId: z.string().min(1),
    quoteExact: z.string().min(1),
    explanation: z.string().min(1),
  })).default([]),
  missingInformation: z.preprocess((value) => value == null ? [] : value, z.array(z.string())).default([]),
  manualReviewNote: z.preprocess((value) => value == null ? "" : value, z.string()).default(""),
});
export type AgentAnswerDraft = z.infer<typeof agentAnswerDraftSchema>;

export const agentRegulatoryBasisSchema = z.object({
  evidenceId: z.string(),
  title: z.string(),
  publisher: z.string().default(""),
  documentNumber: z.string().default(""),
  articleNo: z.string().default(""),
  status: z.string().default(""),
  url: z.string().default(""),
  quoteExact: z.string(),
  explanation: z.string(),
});
export type AgentRegulatoryBasis = z.infer<typeof agentRegulatoryBasisSchema>;

export const agentRegulatoryAnswerSchema = z.object({
  conclusion: z.string(),
  reasoningSummary: z.string(),
  regulatoryBasis: z.array(agentRegulatoryBasisSchema),
  missingInformation: z.array(z.string()).default([]),
  manualReviewNote: z.string().default(""),
  citationValidation: z.object({
    passed: z.boolean(),
    issues: z.array(z.string()),
  }),
});
export type AgentRegulatoryAnswer = z.infer<typeof agentRegulatoryAnswerSchema>;

export const agentTurnStageSchema = z.enum([
  "awaiting_confirmation",
  "awaiting_clarification",
  "complete",
]);
export type AgentTurnStage = z.infer<typeof agentTurnStageSchema>;

export const agentRunTraceSchema = z.object({
  runId: z.string(),
  searchCount: z.number().int().min(0).max(2),
  repairCount: z.number().int().min(0).max(1),
  llmCalls: z.number().int().min(0),
  searchedQueries: z.array(z.string()),
  evidenceIds: z.array(z.string()),
});
export type AgentRunTrace = z.infer<typeof agentRunTraceSchema>;

export const agentChatResponseSchema = z.object({
  sessionId: z.string(),
  stage: agentTurnStageSchema,
  message: z.string(),
  proposedQuery: z.string().optional(),
  answer: agentRegulatoryAnswerSchema.optional(),
  hits: z.array(retrievalHitSchema).default([]),
  trace: agentRunTraceSchema.optional(),
});
export type AgentChatResponse = z.infer<typeof agentChatResponseSchema>;

export const hybridSearchInputSchema = z.object({
  queries: z.array(z.string().min(1)).min(1).max(12),
  subQuestion: z.string().min(1),
  subjects: z.array(z.string()).max(12).default([]),
  productTypes: z.array(z.string()).max(12).default([]),
  counterparties: z.array(z.string()).max(12).default([]),
  timeScope: z.string().default(""),
  requiredEvidence: z.array(z.string()).max(12).default([]),
  topK: z.number().int().min(4).max(20).default(12),
});
export type HybridSearchInput = z.infer<typeof hybridSearchInputSchema>;

// ────────── API 请求/响应 ──────────
export const complianceQueryInputSchema = z.object({
  message: z.string().trim().min(1, "请输入消息").max(4000, "消息过长，请控制在 4000 个字符以内"),
  sessionId: z.string().uuid("sessionId 格式无效").optional(),
  debug: z.boolean().optional().default(false),
}).strict();

export type ComplianceQueryInput = z.infer<typeof complianceQueryInputSchema>;

export const complianceQueryResponseSchema = agentChatResponseSchema;

export type ComplianceQueryResponse = z.infer<
  typeof complianceQueryResponseSchema
>;
