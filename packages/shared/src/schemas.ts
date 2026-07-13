import { z } from "zod";

// ────────── 产品结构 ──────────
export const productStructureSchema = z.object({
  underlyingAsset: z.string().optional().default(""),
  productType: z.string().optional().default(""),
  transactionStructure: z.string().optional().default(""),
  counterparty: z.string().optional().default(""),
  investorType: z.string().optional().default(""),
  isCrossBorder: z.boolean().optional().default(false),
  riskPoints: z.array(z.string()).optional().default([]),
  missingInfo: z.array(z.string()).optional().default([]),
});

export type ProductStructure = z.infer<typeof productStructureSchema>;

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
  isSupplementalContext: z.boolean().optional().default(false),
  subQuestion: z.string().optional().default(""),
});

export type RetrievalHit = z.infer<typeof retrievalHitSchema>;

// ───────── 受控智能体检索状态 ─────────
export const agentStateSchema = z.enum([
  "ANALYZE_QUERY", "PLAN_RETRIEVAL", "RETRIEVE", "ASSESS_EVIDENCE",
  "RETRIEVE_AGAIN", "DRAFT_ANSWER", "VERIFY_DETERMINISTICALLY",
  "REVIEW_ANSWER", "REPAIR_OR_RETRIEVE", "FINALIZE",
]);
export type AgentState = z.infer<typeof agentStateSchema>;

export const retrievalSubQuestionSchema = z.object({
  id: z.string().min(1),
  question: z.string().min(1),
  queries: z.array(z.string().min(1)).min(1).max(8),
  formalTerms: z.array(z.string()).max(16).default([]),
  requiredEvidence: z.array(z.string()).min(1).max(12),
});

export const retrievalPlanSchema = z.object({
  normalizedQuery: z.string().min(1),
  legalIssue: z.string().min(1),
  subjects: z.array(z.string()).max(12).default([]),
  productTypes: z.array(z.string()).max(12).default([]),
  counterparties: z.array(z.string()).max(12).default([]),
  timeScope: z.string().default(""),
  ambiguities: z.array(z.string()).max(12).default([]),
  subQuestions: z.array(retrievalSubQuestionSchema).min(1).max(5),
  reasonSummary: z.string().min(1),
  fallbackUsed: z.boolean().optional().default(false),
});
export type RetrievalPlan = z.infer<typeof retrievalPlanSchema>;

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

const assessmentTextSchema = z.preprocess((value) => {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["question", "type", "description", "reason", "query", "name"]) {
      if (typeof record[key] === "string") return record[key];
    }
    return JSON.stringify(value);
  }
  return String(value ?? "");
}, z.string());

export const evidenceAssessmentSchema = z.object({
  sufficient: z.boolean(),
  answerability: z.enum(["YES", "NO", "UNCERTAIN"]),
  evidenceLevel: z.enum(["DIRECT", "INFERRED", "INSUFFICIENT"]),
  supportedSubQuestions: z.array(assessmentTextSchema).default([]),
  missingSubQuestions: z.array(assessmentTextSchema).default([]),
  missingEvidenceTypes: z.array(assessmentTextSchema).default([]),
  followUpQueries: z.array(assessmentTextSchema).max(12).default([]),
  reasonSummary: z.string().min(1),
});
export type EvidenceAssessment = z.infer<typeof evidenceAssessmentSchema>;

export const answerReviewSchema = z.object({
  verdict: z.enum(["PASS", "REPAIR", "RETRIEVE"]),
  issues: z.array(z.object({
    type: z.string(),
    severity: z.enum(["MINOR", "MAJOR", "CRITICAL"]),
    statement: z.string(),
    evidenceId: z.string().default(""),
    reason: z.string(),
    action: z.string(),
  })).default([]),
  repairInstructions: z.array(z.string()).default([]),
  missingEvidence: z.array(z.string()).default([]),
  followUpQueries: z.array(z.string()).max(12).default([]),
});
export type AnswerReview = z.infer<typeof answerReviewSchema>;

export const agentTraceSchema = z.object({
  states: z.array(z.object({
    state: agentStateSchema,
    summary: z.string(),
    round: z.number().int().optional(),
    toolName: z.string().optional(),
  })),
  retrievalRounds: z.number().int().min(0).max(2),
  repairCount: z.number().int().min(0).max(1),
  reviewCount: z.number().int().min(0).max(2),
  llmCalls: z.number().int().min(0),
  model: z.string(),
  degraded: z.boolean(),
  degradationReason: z.string().optional(),
});
export type AgentTrace = z.infer<typeof agentTraceSchema>;

// ────────── 合规回答 ──────────
export const complianceAnswerSchema = z.object({
  directAnswer: z.enum(["是", "否", "不能确认"]),
  conclusion: z.string(),
  conclusionLabel: z.enum(["可做", "不可做", "有条件可做", "需人工合规复核"]),
  conclusionLevel: z.enum(["明确规定", "基于法规的推导", "证据不足"]).optional().default("证据不足"),
  scope: z.object({
    subject: z.string().default(""),
    product: z.string().default(""),
    counterparty: z.string().default(""),
    time: z.string().default(""),
    conditions: z.array(z.string()).default([]),
  }).optional().default({ subject: "", product: "", counterparty: "", time: "", conditions: [] }),
  productStructure: productStructureSchema,
  regulatoryBasis: z.array(
    z.object({
      title: z.string(),
      evidenceId: z.string(),
      publisher: z.string(),
      url: z.string().optional().default(""),
      articleNo: z.string().optional().default(""),
      excerpt: z.string(),
      requirement: z.string(),
      supportRole: z.enum(["DIRECT_RULE", "BOUNDARY_ONLY", "FUTURE_RULE"]).optional().default("DIRECT_RULE"),
      quoteExact: z.string().optional().default(""),
      status: z.string().optional().default(""),
    })
  ),
  restrictions: z.array(z.string()),
  missingInfo: z.array(z.string()),
  manualReviewNote: z.string().optional().default(""),
  confidenceScore: z.enum(["high", "medium", "low"]).optional().default("medium"),
  confidenceReason: z.string().optional().default(""),
  retrievalTrace: z
    .object({
      chunkHits: z.number(),
      documentHits: z.number(),
      strategy: z.string(),
    })
    .optional(),
  citationValidation: z.object({
    passed: z.boolean(),
    issues: z.array(z.string()),
  }).optional(),
  reviewValidation: z.object({
    passed: z.boolean(),
    verdict: z.enum(["PASS", "REPAIR", "RETRIEVE", "SKIPPED"]),
  }).optional(),
});

export const queryAnalysisSchema = z.object({
  originalQuery: z.string(),
  normalizedQuery: z.string(),
  legalIssue: z.string(),
  businessTypes: z.array(z.string()),
  productTypes: z.array(z.string()),
  subjects: z.array(z.string()),
  regulators: z.array(z.string()),
  timeRange: z.string(),
  asksValidity: z.boolean(),
  topics: z.array(z.string()),
  subQuestions: z.array(z.string()),
  keywords: z.array(z.string()),
  semanticQueries: z.array(z.string()),
});

export type QueryAnalysis = z.infer<typeof queryAnalysisSchema>;

export type ComplianceAnswer = z.infer<typeof complianceAnswerSchema>;

// ────────── API 请求/响应 ──────────
export const complianceQueryInputSchema = z.object({
  query: z.string().min(1, "请输入问题"),
  debug: z.boolean().optional().default(false),
});

export type ComplianceQueryInput = z.infer<typeof complianceQueryInputSchema>;

export const complianceQueryResponseSchema = z.object({
  answer: complianceAnswerSchema,
  hits: z.array(retrievalHitSchema),
  queryAnalysis: queryAnalysisSchema,
  retrievalPlan: retrievalPlanSchema.optional(),
  evidenceAssessment: evidenceAssessmentSchema.optional(),
  reviewResult: answerReviewSchema.optional(),
  agentTrace: agentTraceSchema.optional(),
});

export type ComplianceQueryResponse = z.infer<
  typeof complianceQueryResponseSchema
>;

// ────────── 证据账本条目的 schema（仅用于类型） ──────────
export const evidenceEntrySchema = z.object({
  evidence_id: z.string(),
  source_id: z.string(),
  publisher: z.string(),
  title: z.string(),
  url: z.string().optional().default(""),
  published_at: z.string().optional().default(""),
  effective_at: z.string().optional().default(""),
  status: z.string().optional().default(""),
  body_read: z.boolean().optional().default(false),
  attachment_read: z.boolean().optional().default(false),
  authority_level: z.string().optional().default(""),
  support_scope: z.string().optional().default(""),
  tags: z.array(z.string()).optional().default([]),
  verification_status: z.string().optional().default(""),
  verified_by: z.string().optional().default(""),
});

export type EvidenceEntry = z.infer<typeof evidenceEntrySchema>;

// ────────── 条款条目的 schema ──────────
export const clauseEntrySchema = z.object({
  clause_id: z.string(),
  doc_id: z.string(),
  title: z.string(),
  text: z.string(),
  article_no: z.string().optional().default(""),
  heading_path: z.array(z.string()).optional().default([]),
  publisher: z.string().optional().default(""),
  source_id: z.string().optional().default(""),
  published_at: z.string().optional().default(""),
  effective_at: z.string().optional().default(""),
  retrieved_at: z.string().optional().default(""),
  url: z.string().optional().default(""),
  asset_classes: z.array(z.string()).optional().default([]),
  product_types: z.array(z.string()).optional().default([]),
  authority_level: z.string().optional().default(""),
  status: z.string().optional().default(""),
});

export type ClauseEntry = z.infer<typeof clauseEntrySchema>;
