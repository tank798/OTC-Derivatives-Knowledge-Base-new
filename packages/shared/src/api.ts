// ────────── API 通用响应 ──────────

export type ApiError = {
  message: string;
  code?: string;
};

export type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: ApiError };

// ────────── API 端点类型 ──────────
export type ComplianceQueryRequest = { query: string; debug?: boolean };
export type ComplianceQueryResponseData = import("./schemas").ComplianceQueryResponse;

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
