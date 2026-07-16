"use client";

import { Component, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { complianceQueryResponseSchema, type ComplianceQueryResponseData } from "@otc/shared";
import { queryComplianceStream } from "../lib/api";
import { ChatPanel } from "./chat-panel";
import type { ChatConversation, ChatMessage } from "./chat-types";
import { ConversationSidebar } from "./conversation-sidebar";
import { RegulatorySourcesPanel } from "./regulatory-sources-panel";

const CONVERSATION_STORAGE_KEY = "otc-regulatory-chat-history-v2";
const LEGACY_CONVERSATION_STORAGE_KEY = "otc-regulatory-chat-history-v1";
const MAX_STORED_CONVERSATIONS = 20;

function LoadingSkeleton() {
  return (
    <div className="mx-auto flex h-full max-w-[820px] flex-col items-center justify-center py-16 animate-fade-in">
      <div className="flex flex-col items-center gap-4">
        <div className="h-12 w-12 animate-pulse rounded-full bg-[#e4e4e0]" />
        <div className="h-6 w-64 animate-pulse rounded bg-[#e4e4e0]" />
        <div className="h-4 w-80 animate-pulse rounded bg-[#eeeeeb]" />
      </div>
    </div>
  );
}

type ErrorBoundaryProps = { children: React.ReactNode };
type ErrorBoundaryState = { hasError: boolean; error?: Error };

export class WorkspaceErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="flex h-screen items-center justify-center bg-[#f7f7f5]">
        <div className="mx-auto max-w-md text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#fff0ee] text-[#ad493f]">!</div>
          <h2 className="text-lg font-bold text-[#2d2d29]">应用出现异常</h2>
          <p className="mt-1 text-sm text-[#696963]">请尝试刷新页面</p>
          <p className="mt-3 text-xs text-[#969690]">{this.state.error?.message}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-6 rounded-full bg-[#292926] px-5 py-2.5 text-sm font-medium text-white hover:bg-black"
          >
            刷新页面
          </button>
        </div>
      </div>
    );
  }
}

export function Workspace() {
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [selectedSourceMessageId, setSelectedSourceMessageId] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [input, setInput] = useState("");
  const [isInitializing, setIsInitializing] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const activeConversationIdRef = useRef("");

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId),
    [activeConversationId, conversations],
  );
  const messages = activeConversation?.messages ?? [];
  const selectedSourceMessage = messages.find((message) => message.id === selectedSourceMessageId);
  const selectedAnswer = selectedSourceMessage?.data?.answer;
  const selectedSourceHits = selectedSourceMessage?.data?.hits ?? [];
  const requestRunning = loadingConversationId !== null;

  useEffect(() => {
    const loaded = loadConversations();
    const initialConversations = loaded.length ? loaded : [createConversation()];
    const initialActive = [...initialConversations].sort((left, right) => right.updatedAt - left.updatedAt)[0];
    setConversations(initialConversations);
    setActiveConversationId(initialActive.id);
    activeConversationIdRef.current = initialActive.id;
    const latestAnswerId = findLatestAnswerMessageId(initialActive.messages);
    setSelectedSourceMessageId(latestAnswerId);
    setSourcesOpen(Boolean(latestAnswerId));
    setIsInitializing(false);
  }, []);

  useEffect(() => {
    if (isInitializing || !conversations.length) return;
    persistConversations(conversations);
  }, [conversations, isInitializing]);

  useEffect(() => {
    if (!isInitializing) inputRef.current?.focus();
  }, [activeConversationId, isInitializing]);

  useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  const updateConversation = useCallback((
    conversationId: string,
    updater: (conversation: ChatConversation) => ChatConversation,
  ) => {
    setConversations((previous) => previous.map((conversation) => (
      conversation.id === conversationId ? updater(conversation) : conversation
    )));
  }, []);

  const handleSubmit = useCallback(async (text: string, sessionOverride?: string | null) => {
    const message = text.trim();
    const conversation = conversations.find((item) => item.id === activeConversationId);
    if (!message || requestRunning || !conversation) return;

    const conversationId = conversation.id;
    const activeSessionId = sessionOverride === undefined ? conversation.sessionId : sessionOverride;
    const timestamp = Date.now();
    const userMsg: ChatMessage = { id: `u-${timestamp}-${makeId()}`, role: "user", text: message, status: "done" };
    const assistantMsg: ChatMessage = { id: `a-${timestamp}-${makeId()}`, role: "assistant", text: "", status: "loading" };

    updateConversation(conversationId, (current) => ({
      ...current,
      title: current.messages.some((item) => item.role === "user") ? current.title : titleFromMessage(message),
      updatedAt: timestamp,
      messages: [...current.messages, userMsg, assistantMsg],
    }));
    setInput("");
    setLoadingConversationId(conversationId);

    let streamError = "";
    let streamErrorCode = "";
    let receivedMessage = false;

    const consumeStream = async (sessionId?: string) => {
      streamError = "";
      streamErrorCode = "";
      receivedMessage = false;
      await queryComplianceStream(message, (event) => {
        if (event.type === "progress") {
          updateConversation(conversationId, (current) => ({
            ...current,
            messages: current.messages.map((item) => {
              if (item.id !== assistantMsg.id) return item;
              const progress = [...(item.progress ?? [])];
              const existingIndex = progress.findIndex((step) => step.id === event.data.id);
              if (existingIndex >= 0) progress[existingIndex] = event.data;
              else progress.push(event.data);
              return { ...item, progress };
            }),
          }));
          return;
        }

        if (event.type === "message") {
          receivedMessage = true;
          const displayData = event.data.answer ? compactResponse(event.data) : undefined;
          updateConversation(conversationId, (current) => ({
            ...current,
            sessionId: event.data.sessionId,
            updatedAt: Date.now(),
            messages: current.messages.map((item) => item.id === assistantMsg.id
              ? {
                  ...item,
                  text: event.data.message,
                  status: "done",
                  ...(displayData ? { data: displayData } : {}),
                }
              : item),
          }));
          if (event.data.answer && activeConversationIdRef.current === conversationId) {
            setSelectedSourceMessageId(assistantMsg.id);
            setSourcesOpen(event.data.answer.regulatoryBasis.length > 0);
          }
          return;
        }

        if (event.type === "error") {
          streamError = event.message;
          streamErrorCode = event.code ?? "";
          updateConversation(conversationId, (current) => ({
            ...current,
            messages: current.messages.map((item) => item.id === assistantMsg.id
              ? { ...item, text: event.message, status: "error" }
              : item),
          }));
        }
      }, { sessionId });
    };

    try {
      await consumeStream(activeSessionId ?? undefined);

      if (activeSessionId && (streamErrorCode === "SESSION_EXPIRED" || streamError.includes("对话已失效"))) {
        updateConversation(conversationId, (current) => ({
          ...current,
          sessionId: null,
          messages: current.messages.map((item) => item.id === assistantMsg.id
            ? { ...item, text: "", status: "loading", progress: [] }
            : item),
        }));
        await consumeStream(undefined);
      }

      if (!receivedMessage && !streamError) {
        throw new Error("响应流已结束，但没有收到 Agent 回答");
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "查询失败，请稍后重试";
      updateConversation(conversationId, (current) => ({
        ...current,
        messages: current.messages.map((item) => item.id === assistantMsg.id
          ? { ...item, text: errorMessage, status: "error" }
          : item),
      }));
    } finally {
      setLoadingConversationId(null);
    }
  }, [activeConversationId, conversations, requestRunning, updateConversation]);

  const handleRetry = useCallback((text: string) => {
    const conversationId = activeConversationId;
    updateConversation(conversationId, (current) => {
      const tail = current.messages.slice(-2);
      const messagesWithoutError = tail.length === 2 && tail[0].role === "user" && tail[1].status === "error"
        ? current.messages.slice(0, -2)
        : current.messages;
      return { ...current, messages: messagesWithoutError };
    });
    window.setTimeout(() => void handleSubmit(text), 50);
  }, [activeConversationId, handleSubmit, updateConversation]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void handleSubmit(input);
    }
  }, [handleSubmit, input]);

  const handleNewConversation = useCallback(() => {
    if (activeConversation?.messages.length === 0) {
      setInput("");
      setSourcesOpen(false);
      inputRef.current?.focus();
      return;
    }
    const conversation = createConversation();
    setConversations((previous) => [conversation, ...previous]);
    setActiveConversationId(conversation.id);
    activeConversationIdRef.current = conversation.id;
    setSelectedSourceMessageId(null);
    setSourcesOpen(false);
    setInput("");
  }, [activeConversation]);

  const handleSelectConversation = useCallback((conversationId: string) => {
    const conversation = conversations.find((item) => item.id === conversationId);
    if (!conversation) return;
    const latestAnswerId = findLatestAnswerMessageId(conversation.messages);
    setActiveConversationId(conversationId);
    activeConversationIdRef.current = conversationId;
    setSelectedSourceMessageId(latestAnswerId);
    setSourcesOpen(Boolean(latestAnswerId));
    setInput("");
    updateConversation(conversationId, (current) => ({ ...current, updatedAt: Date.now() }));
  }, [conversations, updateConversation]);

  const handleDeleteConversation = useCallback((conversationId: string) => {
    if (conversationId === loadingConversationId) return;
    const remaining = conversations.filter((conversation) => conversation.id !== conversationId);
    if (!remaining.length) {
      const replacement = createConversation();
      setConversations([replacement]);
      setActiveConversationId(replacement.id);
      activeConversationIdRef.current = replacement.id;
      setSelectedSourceMessageId(null);
      setSourcesOpen(false);
      return;
    }
    setConversations(remaining);
    if (conversationId === activeConversationId) {
      const nextConversation = [...remaining].sort((left, right) => right.updatedAt - left.updatedAt)[0];
      setActiveConversationId(nextConversation.id);
      activeConversationIdRef.current = nextConversation.id;
      setSelectedSourceMessageId(findLatestAnswerMessageId(nextConversation.messages));
      setSourcesOpen(Boolean(findLatestAnswerMessageId(nextConversation.messages)));
    }
  }, [activeConversationId, conversations, loadingConversationId]);

  const handleToggleSources = useCallback(() => {
    setSourcesOpen((current) => {
      if (!current && !selectedSourceMessageId) {
        setSelectedSourceMessageId(findLatestAnswerMessageId(messages));
      }
      return !current;
    });
  }, [messages, selectedSourceMessageId]);

  return (
    <div className="flex h-screen overflow-hidden bg-[#f7f7f5]">
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        loadingConversationId={loadingConversationId}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        {isInitializing || !activeConversation ? (
          <LoadingSkeleton />
        ) : (
          <div className="flex min-h-0 flex-1">
            <section className="min-w-0 flex-1">
              <ChatPanel
                messages={messages}
                loading={requestRunning}
                onSubmit={handleSubmit}
                onRetry={handleRetry}
                input={input}
                setInput={setInput}
                onKeyDown={handleKeyDown}
                inputRef={inputRef}
                scrollRef={scrollRef}
                sourcesOpen={sourcesOpen}
                selectedSourceMessageId={selectedSourceMessageId}
                onOpenSidebar={() => setMobileSidebarOpen(true)}
                onToggleSources={handleToggleSources}
                onSelectSources={(messageId) => {
                  setSelectedSourceMessageId(messageId);
                  setSourcesOpen(true);
                }}
              />
            </section>
            <RegulatorySourcesPanel
              open={sourcesOpen}
              answer={selectedAnswer}
              hits={selectedSourceHits}
              onClose={() => setSourcesOpen(false)}
            />
          </div>
        )}
      </main>
    </div>
  );
}

function createConversation(): ChatConversation {
  const now = Date.now();
  return {
    id: `conversation-${now}-${makeId()}`,
    title: "新对话",
    createdAt: now,
    updatedAt: now,
    sessionId: null,
    messages: [],
  };
}

function makeId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
}

function titleFromMessage(message: string) {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > 28 ? `${normalized.slice(0, 28)}…` : normalized;
}

function findLatestAnswerMessageId(messages: ChatMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].data?.answer) return messages[index].id;
  }
  return null;
}

function compactResponse(data: ComplianceQueryResponseData): ComplianceQueryResponseData {
  const { trace: _trace, ...withoutTrace } = data;
  const citedEvidenceIds = new Set(data.answer?.regulatoryBasis.map((basis) => basis.evidenceId) ?? []);
  return {
    ...withoutTrace,
    hits: data.hits.filter((hit) => citedEvidenceIds.has(hit.id)),
  };
}

function persistConversations(conversations: ChatConversation[]) {
  try {
    const serializable = [...conversations]
      .sort((left, right) => right.updatedAt - left.updatedAt)
      .slice(0, MAX_STORED_CONVERSATIONS)
      .map((conversation) => ({
        ...conversation,
        messages: conversation.messages.map(({ progress: _progress, ...message }) => (
          message.status === "loading"
            ? { ...message, status: "error" as const, text: "回答在页面关闭前中断，请重新发送。" }
            : message
        )),
      }));
    window.sessionStorage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(serializable));
  } catch (error) {
    console.warn("无法保存历史对话", error);
  }
}

function loadConversations(): ChatConversation[] {
  try {
    let raw = window.sessionStorage.getItem(CONVERSATION_STORAGE_KEY);
    if (!raw) {
      raw = window.localStorage.getItem(LEGACY_CONVERSATION_STORAGE_KEY);
      if (raw) window.localStorage.removeItem(LEGACY_CONVERSATION_STORAGE_KEY);
    }
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalizeConversation).filter((item): item is ChatConversation => Boolean(item));
  } catch {
    return [];
  }
}

function normalizeConversation(value: unknown): ChatConversation | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.id !== "string" || !Array.isArray(record.messages)) return null;
  const messages = record.messages.map(normalizeMessage).filter((item): item is ChatMessage => Boolean(item));
  const createdAt = typeof record.createdAt === "number" ? record.createdAt : Date.now();
  return {
    id: record.id,
    title: typeof record.title === "string" && record.title.trim() ? record.title : "新对话",
    createdAt,
    updatedAt: typeof record.updatedAt === "number" ? record.updatedAt : createdAt,
    sessionId: typeof record.sessionId === "string" ? record.sessionId : null,
    messages,
  };
}

function normalizeMessage(value: unknown): ChatMessage | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (
    typeof record.id !== "string"
    || (record.role !== "user" && record.role !== "assistant")
    || typeof record.text !== "string"
  ) return null;
  const status = record.status === "loading" || record.status === "done" || record.status === "error"
    ? record.status
    : undefined;
  const parsedData = record.data && typeof record.data === "object"
    ? complianceQueryResponseSchema.safeParse(record.data)
    : null;
  return {
    id: record.id,
    role: record.role,
    text: record.text,
    ...(status ? { status } : {}),
    ...(parsedData?.success ? { data: parsedData.data } : {}),
  };
}
