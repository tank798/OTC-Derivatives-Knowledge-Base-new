// ────────── API 通用响应 ──────────

export type ApiError = {
  message: string;
  code?: string;
};

export type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: ApiError };

// ────────── API 端点类型 ──────────
export type ComplianceQueryRequest = {
  query: string;
};

export type ComplianceQueryResponseData = {
  queryAnalysis: import("./schemas").QueryAnalysis;
  answer: {
    directAnswer: "是" | "否" | "不能确认";
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
    regulatoryBasis: Array<{
      evidenceId: string;
      title: string;
      publisher: string;
      url: string;
      articleNo: string;
      excerpt: string;
      requirement: string;
      status: string;
    }>;
    restrictions: string[];
    missingInfo: string[];
    manualReviewNote: string;
    retrievalTrace?: {
      chunkHits: number;
      documentHits: number;
      strategy: string;
    };
    citationValidation?: { passed: boolean; issues: string[] };
  };
  hits: Array<{
    source: "evidence" | "clause" | "document" | "chunk";
    id: string;
    documentId: string;
    chunkId: string;
    title: string;
    publisher: string;
    url: string;
    publishedAt: string;
    effectiveAt: string;
    articleNo: string;
    articleEnd: string;
    chapterTitle: string;
    documentNumber: string;
    text: string;
    excerpt: string;
    score: number;
    authorityLevel: string;
    status: string;
    verificationStatus: string;
    matchReason: string;
    retrievalMethods: string[];
    localFilePath: string;
  }>;
};

// ────────── 流式事件（预留） ──────────
export type ComplianceStreamEvent =
  | { type: "thinking"; message: string }
  | { type: "retrieving"; count: number }
  | { type: "product_structure"; data: ComplianceQueryResponseData["answer"]["productStructure"] }
  | { type: "answer_chunk"; content: string }
  | { type: "answer"; data: ComplianceQueryResponseData["answer"] }
  | { type: "hits"; hits: ComplianceQueryResponseData["hits"] }
  | { type: "error"; message: string }
  | { type: "done" };
