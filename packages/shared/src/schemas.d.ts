import { z } from "zod";
export declare const productStructureSchema: z.ZodObject<{
    underlyingAsset: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    productType: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    transactionStructure: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    counterparty: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    investorType: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    isCrossBorder: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    riskPoints: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
    missingInfo: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
}, "strip", z.ZodTypeAny, {
    underlyingAsset: string;
    productType: string;
    transactionStructure: string;
    counterparty: string;
    investorType: string;
    isCrossBorder: boolean;
    riskPoints: string[];
    missingInfo: string[];
}, {
    underlyingAsset?: string | undefined;
    productType?: string | undefined;
    transactionStructure?: string | undefined;
    counterparty?: string | undefined;
    investorType?: string | undefined;
    isCrossBorder?: boolean | undefined;
    riskPoints?: string[] | undefined;
    missingInfo?: string[] | undefined;
}>;
export type ProductStructure = z.infer<typeof productStructureSchema>;
export declare const retrievalHitSchema: z.ZodObject<{
    source: z.ZodEnum<["evidence", "clause", "document"]>;
    id: z.ZodString;
    title: z.ZodString;
    publisher: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    url: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    publishedAt: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    effectiveAt: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    articleNo: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    text: z.ZodString;
    excerpt: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    score: z.ZodNumber;
    authorityLevel: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    verificationStatus: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    matchReason: z.ZodDefault<z.ZodOptional<z.ZodString>>;
}, "strip", z.ZodTypeAny, {
    id: string;
    source: "evidence" | "clause" | "document";
    title: string;
    publisher: string;
    url: string;
    publishedAt: string;
    effectiveAt: string;
    articleNo: string;
    text: string;
    excerpt: string;
    score: number;
    authorityLevel: string;
    verificationStatus: string;
    matchReason: string;
}, {
    id: string;
    source: "evidence" | "clause" | "document";
    title: string;
    text: string;
    score: number;
    publisher?: string | undefined;
    url?: string | undefined;
    publishedAt?: string | undefined;
    effectiveAt?: string | undefined;
    articleNo?: string | undefined;
    excerpt?: string | undefined;
    authorityLevel?: string | undefined;
    verificationStatus?: string | undefined;
    matchReason?: string | undefined;
}>;
export type RetrievalHit = z.infer<typeof retrievalHitSchema>;
export declare const complianceAnswerSchema: z.ZodObject<{
    conclusion: z.ZodString;
    conclusionLabel: z.ZodEnum<["可做", "不可做", "有条件可做", "需人工合规复核"]>;
    productStructure: z.ZodObject<{
        underlyingAsset: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        productType: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        transactionStructure: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        counterparty: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        investorType: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        isCrossBorder: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
        riskPoints: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
        missingInfo: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
    }, "strip", z.ZodTypeAny, {
        underlyingAsset: string;
        productType: string;
        transactionStructure: string;
        counterparty: string;
        investorType: string;
        isCrossBorder: boolean;
        riskPoints: string[];
        missingInfo: string[];
    }, {
        underlyingAsset?: string | undefined;
        productType?: string | undefined;
        transactionStructure?: string | undefined;
        counterparty?: string | undefined;
        investorType?: string | undefined;
        isCrossBorder?: boolean | undefined;
        riskPoints?: string[] | undefined;
        missingInfo?: string[] | undefined;
    }>;
    regulatoryBasis: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        publisher: z.ZodString;
        url: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        articleNo: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        excerpt: z.ZodString;
        requirement: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        title: string;
        publisher: string;
        url: string;
        articleNo: string;
        excerpt: string;
        requirement: string;
    }, {
        title: string;
        publisher: string;
        excerpt: string;
        requirement: string;
        url?: string | undefined;
        articleNo?: string | undefined;
    }>, "many">;
    restrictions: z.ZodArray<z.ZodString, "many">;
    missingInfo: z.ZodArray<z.ZodString, "many">;
    manualReviewNote: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    retrievalTrace: z.ZodOptional<z.ZodObject<{
        evidenceHits: z.ZodNumber;
        clauseHits: z.ZodNumber;
        documentHits: z.ZodNumber;
        strategy: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        evidenceHits: number;
        clauseHits: number;
        documentHits: number;
        strategy: string;
    }, {
        evidenceHits: number;
        clauseHits: number;
        documentHits: number;
        strategy: string;
    }>>;
}, "strip", z.ZodTypeAny, {
    missingInfo: string[];
    conclusion: string;
    conclusionLabel: "可做" | "不可做" | "有条件可做" | "需人工合规复核";
    productStructure: {
        underlyingAsset: string;
        productType: string;
        transactionStructure: string;
        counterparty: string;
        investorType: string;
        isCrossBorder: boolean;
        riskPoints: string[];
        missingInfo: string[];
    };
    regulatoryBasis: {
        title: string;
        publisher: string;
        url: string;
        articleNo: string;
        excerpt: string;
        requirement: string;
    }[];
    restrictions: string[];
    manualReviewNote: string;
    retrievalTrace?: {
        evidenceHits: number;
        clauseHits: number;
        documentHits: number;
        strategy: string;
    } | undefined;
}, {
    missingInfo: string[];
    conclusion: string;
    conclusionLabel: "可做" | "不可做" | "有条件可做" | "需人工合规复核";
    productStructure: {
        underlyingAsset?: string | undefined;
        productType?: string | undefined;
        transactionStructure?: string | undefined;
        counterparty?: string | undefined;
        investorType?: string | undefined;
        isCrossBorder?: boolean | undefined;
        riskPoints?: string[] | undefined;
        missingInfo?: string[] | undefined;
    };
    regulatoryBasis: {
        title: string;
        publisher: string;
        excerpt: string;
        requirement: string;
        url?: string | undefined;
        articleNo?: string | undefined;
    }[];
    restrictions: string[];
    manualReviewNote?: string | undefined;
    retrievalTrace?: {
        evidenceHits: number;
        clauseHits: number;
        documentHits: number;
        strategy: string;
    } | undefined;
}>;
export type ComplianceAnswer = z.infer<typeof complianceAnswerSchema>;
export declare const complianceQueryInputSchema: z.ZodObject<{
    query: z.ZodString;
}, "strip", z.ZodTypeAny, {
    query: string;
}, {
    query: string;
}>;
export type ComplianceQueryInput = z.infer<typeof complianceQueryInputSchema>;
export declare const complianceQueryResponseSchema: z.ZodObject<{
    answer: z.ZodObject<{
        conclusion: z.ZodString;
        conclusionLabel: z.ZodEnum<["可做", "不可做", "有条件可做", "需人工合规复核"]>;
        productStructure: z.ZodObject<{
            underlyingAsset: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            productType: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            transactionStructure: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            counterparty: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            investorType: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            isCrossBorder: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
            riskPoints: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
            missingInfo: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
        }, "strip", z.ZodTypeAny, {
            underlyingAsset: string;
            productType: string;
            transactionStructure: string;
            counterparty: string;
            investorType: string;
            isCrossBorder: boolean;
            riskPoints: string[];
            missingInfo: string[];
        }, {
            underlyingAsset?: string | undefined;
            productType?: string | undefined;
            transactionStructure?: string | undefined;
            counterparty?: string | undefined;
            investorType?: string | undefined;
            isCrossBorder?: boolean | undefined;
            riskPoints?: string[] | undefined;
            missingInfo?: string[] | undefined;
        }>;
        regulatoryBasis: z.ZodArray<z.ZodObject<{
            title: z.ZodString;
            publisher: z.ZodString;
            url: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            articleNo: z.ZodDefault<z.ZodOptional<z.ZodString>>;
            excerpt: z.ZodString;
            requirement: z.ZodString;
        }, "strip", z.ZodTypeAny, {
            title: string;
            publisher: string;
            url: string;
            articleNo: string;
            excerpt: string;
            requirement: string;
        }, {
            title: string;
            publisher: string;
            excerpt: string;
            requirement: string;
            url?: string | undefined;
            articleNo?: string | undefined;
        }>, "many">;
        restrictions: z.ZodArray<z.ZodString, "many">;
        missingInfo: z.ZodArray<z.ZodString, "many">;
        manualReviewNote: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        retrievalTrace: z.ZodOptional<z.ZodObject<{
            evidenceHits: z.ZodNumber;
            clauseHits: z.ZodNumber;
            documentHits: z.ZodNumber;
            strategy: z.ZodString;
        }, "strip", z.ZodTypeAny, {
            evidenceHits: number;
            clauseHits: number;
            documentHits: number;
            strategy: string;
        }, {
            evidenceHits: number;
            clauseHits: number;
            documentHits: number;
            strategy: string;
        }>>;
    }, "strip", z.ZodTypeAny, {
        missingInfo: string[];
        conclusion: string;
        conclusionLabel: "可做" | "不可做" | "有条件可做" | "需人工合规复核";
        productStructure: {
            underlyingAsset: string;
            productType: string;
            transactionStructure: string;
            counterparty: string;
            investorType: string;
            isCrossBorder: boolean;
            riskPoints: string[];
            missingInfo: string[];
        };
        regulatoryBasis: {
            title: string;
            publisher: string;
            url: string;
            articleNo: string;
            excerpt: string;
            requirement: string;
        }[];
        restrictions: string[];
        manualReviewNote: string;
        retrievalTrace?: {
            evidenceHits: number;
            clauseHits: number;
            documentHits: number;
            strategy: string;
        } | undefined;
    }, {
        missingInfo: string[];
        conclusion: string;
        conclusionLabel: "可做" | "不可做" | "有条件可做" | "需人工合规复核";
        productStructure: {
            underlyingAsset?: string | undefined;
            productType?: string | undefined;
            transactionStructure?: string | undefined;
            counterparty?: string | undefined;
            investorType?: string | undefined;
            isCrossBorder?: boolean | undefined;
            riskPoints?: string[] | undefined;
            missingInfo?: string[] | undefined;
        };
        regulatoryBasis: {
            title: string;
            publisher: string;
            excerpt: string;
            requirement: string;
            url?: string | undefined;
            articleNo?: string | undefined;
        }[];
        restrictions: string[];
        manualReviewNote?: string | undefined;
        retrievalTrace?: {
            evidenceHits: number;
            clauseHits: number;
            documentHits: number;
            strategy: string;
        } | undefined;
    }>;
    hits: z.ZodArray<z.ZodObject<{
        source: z.ZodEnum<["evidence", "clause", "document"]>;
        id: z.ZodString;
        title: z.ZodString;
        publisher: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        url: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        publishedAt: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        effectiveAt: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        articleNo: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        text: z.ZodString;
        excerpt: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        score: z.ZodNumber;
        authorityLevel: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        verificationStatus: z.ZodDefault<z.ZodOptional<z.ZodString>>;
        matchReason: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        source: "evidence" | "clause" | "document";
        title: string;
        publisher: string;
        url: string;
        publishedAt: string;
        effectiveAt: string;
        articleNo: string;
        text: string;
        excerpt: string;
        score: number;
        authorityLevel: string;
        verificationStatus: string;
        matchReason: string;
    }, {
        id: string;
        source: "evidence" | "clause" | "document";
        title: string;
        text: string;
        score: number;
        publisher?: string | undefined;
        url?: string | undefined;
        publishedAt?: string | undefined;
        effectiveAt?: string | undefined;
        articleNo?: string | undefined;
        excerpt?: string | undefined;
        authorityLevel?: string | undefined;
        verificationStatus?: string | undefined;
        matchReason?: string | undefined;
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    answer: {
        missingInfo: string[];
        conclusion: string;
        conclusionLabel: "可做" | "不可做" | "有条件可做" | "需人工合规复核";
        productStructure: {
            underlyingAsset: string;
            productType: string;
            transactionStructure: string;
            counterparty: string;
            investorType: string;
            isCrossBorder: boolean;
            riskPoints: string[];
            missingInfo: string[];
        };
        regulatoryBasis: {
            title: string;
            publisher: string;
            url: string;
            articleNo: string;
            excerpt: string;
            requirement: string;
        }[];
        restrictions: string[];
        manualReviewNote: string;
        retrievalTrace?: {
            evidenceHits: number;
            clauseHits: number;
            documentHits: number;
            strategy: string;
        } | undefined;
    };
    hits: {
        id: string;
        source: "evidence" | "clause" | "document";
        title: string;
        publisher: string;
        url: string;
        publishedAt: string;
        effectiveAt: string;
        articleNo: string;
        text: string;
        excerpt: string;
        score: number;
        authorityLevel: string;
        verificationStatus: string;
        matchReason: string;
    }[];
}, {
    answer: {
        missingInfo: string[];
        conclusion: string;
        conclusionLabel: "可做" | "不可做" | "有条件可做" | "需人工合规复核";
        productStructure: {
            underlyingAsset?: string | undefined;
            productType?: string | undefined;
            transactionStructure?: string | undefined;
            counterparty?: string | undefined;
            investorType?: string | undefined;
            isCrossBorder?: boolean | undefined;
            riskPoints?: string[] | undefined;
            missingInfo?: string[] | undefined;
        };
        regulatoryBasis: {
            title: string;
            publisher: string;
            excerpt: string;
            requirement: string;
            url?: string | undefined;
            articleNo?: string | undefined;
        }[];
        restrictions: string[];
        manualReviewNote?: string | undefined;
        retrievalTrace?: {
            evidenceHits: number;
            clauseHits: number;
            documentHits: number;
            strategy: string;
        } | undefined;
    };
    hits: {
        id: string;
        source: "evidence" | "clause" | "document";
        title: string;
        text: string;
        score: number;
        publisher?: string | undefined;
        url?: string | undefined;
        publishedAt?: string | undefined;
        effectiveAt?: string | undefined;
        articleNo?: string | undefined;
        excerpt?: string | undefined;
        authorityLevel?: string | undefined;
        verificationStatus?: string | undefined;
        matchReason?: string | undefined;
    }[];
}>;
export type ComplianceQueryResponse = z.infer<typeof complianceQueryResponseSchema>;
export declare const evidenceEntrySchema: z.ZodObject<{
    evidence_id: z.ZodString;
    source_id: z.ZodString;
    publisher: z.ZodString;
    title: z.ZodString;
    url: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    published_at: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    effective_at: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    body_read: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    attachment_read: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    authority_level: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    support_scope: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    tags: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
    verification_status: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    verified_by: z.ZodDefault<z.ZodOptional<z.ZodString>>;
}, "strip", z.ZodTypeAny, {
    title: string;
    publisher: string;
    url: string;
    evidence_id: string;
    source_id: string;
    published_at: string;
    effective_at: string;
    body_read: boolean;
    attachment_read: boolean;
    authority_level: string;
    support_scope: string;
    tags: string[];
    verification_status: string;
    verified_by: string;
}, {
    title: string;
    publisher: string;
    evidence_id: string;
    source_id: string;
    url?: string | undefined;
    published_at?: string | undefined;
    effective_at?: string | undefined;
    body_read?: boolean | undefined;
    attachment_read?: boolean | undefined;
    authority_level?: string | undefined;
    support_scope?: string | undefined;
    tags?: string[] | undefined;
    verification_status?: string | undefined;
    verified_by?: string | undefined;
}>;
export type EvidenceEntry = z.infer<typeof evidenceEntrySchema>;
export declare const clauseEntrySchema: z.ZodObject<{
    clause_id: z.ZodString;
    doc_id: z.ZodString;
    title: z.ZodString;
    text: z.ZodString;
    article_no: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    heading_path: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
    publisher: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    source_id: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    published_at: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    retrieved_at: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    url: z.ZodDefault<z.ZodOptional<z.ZodString>>;
    asset_classes: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
    product_types: z.ZodDefault<z.ZodOptional<z.ZodArray<z.ZodString, "many">>>;
    authority_level: z.ZodDefault<z.ZodOptional<z.ZodString>>;
}, "strip", z.ZodTypeAny, {
    title: string;
    publisher: string;
    url: string;
    text: string;
    source_id: string;
    published_at: string;
    authority_level: string;
    clause_id: string;
    doc_id: string;
    article_no: string;
    heading_path: string[];
    retrieved_at: string;
    asset_classes: string[];
    product_types: string[];
}, {
    title: string;
    text: string;
    clause_id: string;
    doc_id: string;
    publisher?: string | undefined;
    url?: string | undefined;
    source_id?: string | undefined;
    published_at?: string | undefined;
    authority_level?: string | undefined;
    article_no?: string | undefined;
    heading_path?: string[] | undefined;
    retrieved_at?: string | undefined;
    asset_classes?: string[] | undefined;
    product_types?: string[] | undefined;
}>;
export type ClauseEntry = z.infer<typeof clauseEntrySchema>;
//# sourceMappingURL=schemas.d.ts.map