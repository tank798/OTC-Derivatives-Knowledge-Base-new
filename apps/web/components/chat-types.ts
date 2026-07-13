import type { AgentProgressEvent, ComplianceQueryResponseData } from "@otc/shared";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "loading" | "done" | "error";
  data?: ComplianceQueryResponseData;
  progress?: AgentProgressEvent[];
};

export type ChatConversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  sessionId: string | null;
  messages: ChatMessage[];
};
