import type { AgentProgressEvent, ComplianceQueryResponseData } from "@otc/shared";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "loading" | "done" | "error";
  data?: ComplianceQueryResponseData;
  progress?: AgentProgressEvent[];
  feedback?: "helpful" | "badcase";
};

export type ChatConversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  sessionId: string | null;
  draft: string;
  messages: ChatMessage[];
};

export type BadcaseRecord = {
  id: string;
  conversationId: string;
  messageId: string;
  question: string;
  answer: string;
  note: string;
  references: Array<{
    kind: "regulation" | "wiki";
    title: string;
    locator: string;
    quote: string;
    explanation: string;
    url: string;
  }>;
  createdAt: number;
  status: "open" | "resolved";
};
