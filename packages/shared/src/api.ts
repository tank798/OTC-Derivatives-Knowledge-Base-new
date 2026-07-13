// ────────── API 通用响应 ──────────

export type ApiError = {
  message: string;
  code?: string;
};

export type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: ApiError };

// ────────── API 端点类型 ──────────
export type ComplianceQueryRequest = { message: string; sessionId?: string; debug?: boolean };
export type ComplianceQueryResponseData = import("./schemas").AgentChatResponse;

export type AgentProgressEvent = {
  id: string;
  label: string;
  status: "running" | "done";
  detail?: string;
};

// ────────── 流式事件 ──────────
export type ComplianceStreamEvent =
  | { type: "progress"; data: AgentProgressEvent }
  | { type: "message"; data: ComplianceQueryResponseData }
  | { type: "answer"; data: NonNullable<ComplianceQueryResponseData["answer"]> }
  | { type: "hits"; hits: ComplianceQueryResponseData["hits"] }
  | { type: "error"; message: string }
  | { type: "done" };
