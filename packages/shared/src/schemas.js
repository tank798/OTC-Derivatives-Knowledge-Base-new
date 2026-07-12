"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.clauseEntrySchema = exports.evidenceEntrySchema = exports.complianceQueryResponseSchema = exports.complianceQueryInputSchema = exports.complianceAnswerSchema = exports.retrievalHitSchema = exports.productStructureSchema = void 0;
const zod_1 = require("zod");
// ────────── 产品结构 ──────────
exports.productStructureSchema = zod_1.z.object({
    underlyingAsset: zod_1.z.string().optional().default(""),
    productType: zod_1.z.string().optional().default(""),
    transactionStructure: zod_1.z.string().optional().default(""),
    counterparty: zod_1.z.string().optional().default(""),
    investorType: zod_1.z.string().optional().default(""),
    isCrossBorder: zod_1.z.boolean().optional().default(false),
    riskPoints: zod_1.z.array(zod_1.z.string()).optional().default([]),
    missingInfo: zod_1.z.array(zod_1.z.string()).optional().default([]),
});
// ────────── 检索命中 ──────────
exports.retrievalHitSchema = zod_1.z.object({
    source: zod_1.z.enum(["evidence", "clause", "document"]),
    id: zod_1.z.string(),
    title: zod_1.z.string(),
    publisher: zod_1.z.string().optional().default(""),
    url: zod_1.z.string().optional().default(""),
    publishedAt: zod_1.z.string().optional().default(""),
    effectiveAt: zod_1.z.string().optional().default(""),
    articleNo: zod_1.z.string().optional().default(""),
    text: zod_1.z.string(),
    excerpt: zod_1.z.string().optional().default(""),
    score: zod_1.z.number(),
    authorityLevel: zod_1.z.string().optional().default(""),
    verificationStatus: zod_1.z.string().optional().default(""),
    matchReason: zod_1.z.string().optional().default(""),
});
// ────────── 合规回答 ──────────
exports.complianceAnswerSchema = zod_1.z.object({
    conclusion: zod_1.z.string(),
    conclusionLabel: zod_1.z.enum(["可做", "不可做", "有条件可做", "需人工合规复核"]),
    productStructure: exports.productStructureSchema,
    regulatoryBasis: zod_1.z.array(zod_1.z.object({
        title: zod_1.z.string(),
        publisher: zod_1.z.string(),
        url: zod_1.z.string().optional().default(""),
        articleNo: zod_1.z.string().optional().default(""),
        excerpt: zod_1.z.string(),
        requirement: zod_1.z.string(),
    })),
    restrictions: zod_1.z.array(zod_1.z.string()),
    missingInfo: zod_1.z.array(zod_1.z.string()),
    manualReviewNote: zod_1.z.string().optional().default(""),
    retrievalTrace: zod_1.z
        .object({
        evidenceHits: zod_1.z.number(),
        clauseHits: zod_1.z.number(),
        documentHits: zod_1.z.number(),
        strategy: zod_1.z.string(),
    })
        .optional(),
});
// ────────── API 请求/响应 ──────────
exports.complianceQueryInputSchema = zod_1.z.object({
    query: zod_1.z.string().min(1, "请输入问题"),
});
exports.complianceQueryResponseSchema = zod_1.z.object({
    answer: exports.complianceAnswerSchema,
    hits: zod_1.z.array(exports.retrievalHitSchema),
});
// ────────── 证据账本条目的 schema（仅用于类型） ──────────
exports.evidenceEntrySchema = zod_1.z.object({
    evidence_id: zod_1.z.string(),
    source_id: zod_1.z.string(),
    publisher: zod_1.z.string(),
    title: zod_1.z.string(),
    url: zod_1.z.string().optional().default(""),
    published_at: zod_1.z.string().optional().default(""),
    effective_at: zod_1.z.string().optional().default(""),
    body_read: zod_1.z.boolean().optional().default(false),
    attachment_read: zod_1.z.boolean().optional().default(false),
    authority_level: zod_1.z.string().optional().default(""),
    support_scope: zod_1.z.string().optional().default(""),
    tags: zod_1.z.array(zod_1.z.string()).optional().default([]),
    verification_status: zod_1.z.string().optional().default(""),
    verified_by: zod_1.z.string().optional().default(""),
});
// ────────── 条款条目的 schema ──────────
exports.clauseEntrySchema = zod_1.z.object({
    clause_id: zod_1.z.string(),
    doc_id: zod_1.z.string(),
    title: zod_1.z.string(),
    text: zod_1.z.string(),
    article_no: zod_1.z.string().optional().default(""),
    heading_path: zod_1.z.array(zod_1.z.string()).optional().default([]),
    publisher: zod_1.z.string().optional().default(""),
    source_id: zod_1.z.string().optional().default(""),
    published_at: zod_1.z.string().optional().default(""),
    retrieved_at: zod_1.z.string().optional().default(""),
    url: zod_1.z.string().optional().default(""),
    asset_classes: zod_1.z.array(zod_1.z.string()).optional().default([]),
    product_types: zod_1.z.array(zod_1.z.string()).optional().default([]),
    authority_level: zod_1.z.string().optional().default(""),
});
//# sourceMappingURL=schemas.js.map