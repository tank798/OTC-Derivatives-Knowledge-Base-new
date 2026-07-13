"use client";

import { useEffect, type RefObject } from "react";
import type { ChatMessage } from "./chat-types";
import { ComplianceAnswerCard } from "./compliance-answer-card";
import { ThinkingBubble } from "./thinking-bubble";

type Props = {
  messages: ChatMessage[];
  loading: boolean;
  onSubmit: (text: string) => void;
  onRetry: (text: string) => void;
  input: string;
  setInput: (value: string) => void;
  onKeyDown: (event: React.KeyboardEvent) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  scrollRef: RefObject<HTMLDivElement | null>;
  sourcesOpen: boolean;
  selectedSourceMessageId: string | null;
  onOpenSidebar: () => void;
  onToggleSources: () => void;
  onSelectSources: (messageId: string) => void;
};

const EXAMPLE_TAGS = [
  "上市公司可以做挂钩自己股票的场外衍生品吗？",
  "券商收益凭证可以做雪球吗？",
  "私募产品投资雪球的比例有明确规定吗？",
];

export function ChatPanel({
  messages,
  loading,
  onSubmit,
  onRetry,
  input,
  setInput,
  onKeyDown,
  inputRef,
  scrollRef,
  sourcesOpen,
  selectedSourceMessageId,
  onOpenSidebar,
  onToggleSources,
  onSelectSources,
}: Props) {
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, scrollRef]);

  useEffect(() => {
    if (!input && inputRef.current) inputRef.current.style.height = "auto";
  }, [input, inputRef]);

  const showWelcome = messages.length === 0;

  const fillExampleQuestion = (question: string) => {
    setInput(question);
    window.requestAnimationFrame(() => {
      if (!inputRef.current) return;
      inputRef.current.focus();
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 144)}px`;
    });
  };

  return (
    <div className="relative flex h-full w-full flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-transparent px-3 sm:px-5">
        <div className="flex min-w-0 items-center">
          <button
            type="button"
            onClick={onOpenSidebar}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[#696963] transition-colors hover:bg-[#ecece8] lg:hidden"
            aria-label="打开历史对话"
          >
            <SidebarIcon />
          </button>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="hidden items-center gap-2 px-2 text-[11px] text-[#979791] sm:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[#68a86b]" />
            法规库已连接
          </div>
          {!sourcesOpen && (
            <button
              type="button"
              onClick={onToggleSources}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-transparent text-[#74746e] transition-colors hover:bg-[#ecece8] hover:text-[#343430]"
              aria-label="显示法规依据"
              title="显示法规依据"
            >
              <SourcesPanelToggleIcon />
            </button>
          )}
        </div>
      </header>

      <div ref={scrollRef} className="scrollbar-hidden flex-1 overflow-y-auto px-5 sm:px-8">
        {showWelcome ? (
          <div className="mx-auto flex min-h-full w-full max-w-[780px] flex-col items-center justify-center pb-20 text-center">
            <h1 className="text-[28px] font-medium leading-tight tracking-[-0.035em] text-[#242421] sm:text-[32px]">
              有什么可以帮忙的？
            </h1>
            <div className="mt-8 w-full">
              <Composer
                input={input}
                setInput={setInput}
                onKeyDown={onKeyDown}
                onSubmit={onSubmit}
                inputRef={inputRef}
                loading={loading}
              />
            </div>
            <div className="mt-5 flex max-w-[720px] flex-wrap justify-center gap-2">
              {EXAMPLE_TAGS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => fillExampleQuestion(question)}
                  className="rounded-full bg-[#ededeb] px-3.5 py-2 text-left text-[13px] leading-5 text-[#666660] transition-colors hover:bg-[#e2e2df] hover:text-[#292926]"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-[780px] space-y-8 pb-8 pt-5">
            {messages.map((message, index) => {
              const retryQuery = message.role === "assistant" && message.status === "error"
                ? findPreviousUserMessage(messages, index)
                : "";

              if (message.role === "user") {
                return (
                  <div key={message.id} className="flex animate-fade-in justify-end">
                    <div className="max-w-[82%] rounded-[22px] bg-[#e9e9e7] px-5 py-3 text-[15px] leading-7 text-[#292926]">
                      {message.text}
                    </div>
                  </div>
                );
              }

              return (
                <div key={message.id} className="w-full animate-fade-in">
                  <ThinkingBubble progress={message.progress} active={message.status === "loading"} />

                  {message.status === "loading" ? null : message.status === "error" ? (
                    <div className="rounded-2xl border border-[#e3c8c4] bg-[#fffafa] p-4 text-sm text-[#8b3b32]">
                      <p className="font-medium">查询没有完成</p>
                      <p className="mt-1 leading-6 text-[#9b5a52]">{message.text}</p>
                      {retryQuery && (
                        <button
                          onClick={() => onRetry(retryQuery)}
                          className="mt-3 rounded-full border border-[#dbbbb6] bg-white px-3.5 py-1.5 text-xs font-medium transition-colors hover:bg-[#fff5f3]"
                        >
                          重新发送
                        </button>
                      )}
                    </div>
                  ) : message.data ? (
                    <ComplianceAnswerCard
                      data={message.data}
                      sourcesSelected={message.id === selectedSourceMessageId && sourcesOpen}
                      onShowSources={() => onSelectSources(message.id)}
                    />
                  ) : (
                    <div className="max-w-[700px] whitespace-pre-wrap text-[15px] leading-7 text-[#343431]">
                      {message.text}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {!showWelcome && (
        <div className="shrink-0 bg-gradient-to-t from-[#f7f7f5] via-[#f7f7f5] to-transparent px-4 pb-3 pt-4 sm:px-8 sm:pb-4">
          <div className="mx-auto max-w-[780px]">
            <Composer
              input={input}
              setInput={setInput}
              onKeyDown={onKeyDown}
              onSubmit={onSubmit}
              inputRef={inputRef}
              loading={loading}
            />
            <p className="mt-2 text-center text-[11px] text-[#aaa9a3]">回答仅供参考，请核验重要信息。</p>
          </div>
        </div>
      )}
    </div>
  );
}

function findPreviousUserMessage(messages: ChatMessage[], index: number) {
  for (let position = index - 1; position >= 0; position -= 1) {
    if (messages[position].role === "user") return messages[position].text;
  }
  return "";
}

type ComposerProps = {
  input: string;
  setInput: (value: string) => void;
  onKeyDown: (event: React.KeyboardEvent) => void;
  onSubmit: (text: string) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  loading: boolean;
};

function Composer({ input, setInput, onKeyDown, onSubmit, inputRef, loading }: ComposerProps) {
  return (
    <div className="flex items-end gap-3 rounded-[26px] border border-[#dfdfdc] bg-white px-4 py-2.5 shadow-[0_7px_24px_rgba(39,39,35,0.07)] transition-all focus-within:border-[#c5c5c0] focus-within:shadow-[0_9px_30px_rgba(39,39,35,0.1)]">
      <textarea
        ref={inputRef}
        value={input}
        onChange={(event) => {
          setInput(event.target.value);
          event.currentTarget.style.height = "auto";
          event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 144)}px`;
        }}
        onKeyDown={onKeyDown}
        placeholder="输入你的问题"
        rows={1}
        className="max-h-36 min-h-[36px] flex-1 resize-none overflow-y-auto bg-transparent px-1 py-1.5 text-[16px] leading-6 text-[#242421] outline-none placeholder:text-[#9d9d98]"
        disabled={loading}
      />
      <button
        type="button"
        onClick={() => onSubmit(input)}
        disabled={loading || !input.trim()}
        className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#242422] text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:bg-[#d0d0cc]"
        aria-label="发送"
      >
        {loading ? <span className="agent-button-breath h-2 w-2 rounded-full bg-white" /> : <ArrowUpIcon />}
      </button>
    </div>
  );
}

function ArrowUpIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 15V5m0 0L6 9m4-4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SidebarIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.35" />
      <path d="M7.5 4v12" stroke="currentColor" strokeWidth="1.35" />
    </svg>
  );
}

function SourcesPanelToggleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.35" />
      <path d="M12.5 4v12" stroke="currentColor" strokeWidth="1.35" />
      <path d="m6.5 7 2.5 3-2.5 3" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
