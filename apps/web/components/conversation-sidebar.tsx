"use client";

import { useEffect, useMemo, useState } from "react";
import type { ChatConversation } from "./chat-types";

type Props = {
  conversations: ChatConversation[];
  activeConversationId: string;
  loadingConversationId: string | null;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
};

type ContextMenuState = { id: string; x: number; y: number } | null;

export function ConversationSidebar({
  conversations,
  activeConversationId,
  loadingConversationId,
  mobileOpen,
  onCloseMobile,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
}: Props) {
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const sortedConversations = useMemo(
    () => [...conversations].sort((left, right) => right.updatedAt - left.updatedAt),
    [conversations],
  );

  useEffect(() => {
    const closeMenu = () => setContextMenu(null);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setContextMenu(null);
        setPendingDeleteId(null);
      }
    };
    window.addEventListener("click", closeMenu);
    window.addEventListener("resize", closeMenu);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("click", closeMenu);
      window.removeEventListener("resize", closeMenu);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const openContextMenu = (id: string, x: number, y: number) => {
    const menuWidth = 164;
    const menuHeight = 52;
    setContextMenu({
      id,
      x: Math.min(x, window.innerWidth - menuWidth - 10),
      y: Math.min(y, window.innerHeight - menuHeight - 10),
    });
  };

  const pendingConversation = pendingDeleteId
    ? conversations.find((conversation) => conversation.id === pendingDeleteId)
    : undefined;

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="关闭历史对话"
          className="fixed inset-0 z-30 bg-black/20 backdrop-blur-[1px] lg:hidden"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[268px] flex-col border-r border-[#deded9] bg-[#efefec] transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 shrink-0 items-center px-3.5">
          <p className="truncate px-2 text-[15px] font-semibold tracking-[-0.01em] text-[#2b2b28]">
            场外衍生品法规助手
          </p>
        </div>

        <div className="px-3 pb-2">
          <button
            type="button"
            onClick={() => {
              onNewConversation();
              onCloseMobile();
            }}
            className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-[14px] font-medium text-[#373733] transition-colors hover:bg-[#e2e2de]"
          >
            <NewChatIcon />
            新对话
          </button>
        </div>

        <div className="px-5 pb-2 pt-3 text-[11px] font-medium tracking-[0.08em] text-[#969690]">最近</div>

        <nav className="scrollbar-hidden flex-1 overflow-y-auto px-2.5 pb-4" aria-label="历史对话">
          <div className="space-y-1">
            {sortedConversations.map((conversation) => {
              const active = conversation.id === activeConversationId;
              const running = conversation.id === loadingConversationId;
              return (
                <div
                  key={conversation.id}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    openContextMenu(conversation.id, event.clientX, event.clientY);
                  }}
                  className={`group relative rounded-xl transition-colors ${active ? "bg-white/85 shadow-[0_1px_2px_rgba(30,30,26,0.04)]" : "hover:bg-[#e4e4e0]"}`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      onSelectConversation(conversation.id);
                      onCloseMobile();
                    }}
                    className="w-full px-3 py-2.5 pr-10 text-left"
                  >
                    <span className={`block truncate text-[13px] leading-5 ${active ? "font-medium text-[#292926]" : "text-[#555550]"}`}>
                      {conversation.title}
                    </span>
                    {!running && (
                      <span className="mt-0.5 block text-[10px] text-[#a0a09a]">
                        {formatConversationTime(conversation.updatedAt)}
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    aria-label={`管理对话：${conversation.title}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      const rect = event.currentTarget.getBoundingClientRect();
                      openContextMenu(conversation.id, rect.right - 160, rect.bottom + 5);
                    }}
                    className={`absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-lg text-[#777771] transition-opacity hover:bg-[#d5d5d0] hover:text-[#2f2f2b] ${active ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                  >
                    <MoreIcon />
                  </button>
                </div>
              );
            })}
          </div>
        </nav>

      </aside>

      {contextMenu && (
        <div
          role="menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          className="fixed z-[70] w-[164px] rounded-xl border border-[#deded8] bg-white p-1.5 shadow-[0_14px_40px_rgba(31,31,27,0.15)]"
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            role="menuitem"
            disabled={contextMenu.id === loadingConversationId}
            onClick={() => {
              setPendingDeleteId(contextMenu.id);
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] text-[#a13f37] transition-colors hover:bg-[#fff1ef] disabled:cursor-not-allowed disabled:text-[#b9b9b3] disabled:hover:bg-transparent"
          >
            <TrashIcon />
            {contextMenu.id === loadingConversationId ? "回答中不可删除" : "删除对话"}
          </button>
        </div>
      )}

      {pendingConversation && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/20 px-5 backdrop-blur-[1px]">
          <div className="w-full max-w-[390px] rounded-2xl border border-[#deded9] bg-[#fbfbfa] p-5 shadow-[0_24px_70px_rgba(28,28,24,0.2)]">
            <h2 className="text-[16px] font-semibold text-[#292926]">删除这条对话？</h2>
            <p className="mt-2 line-clamp-2 text-[13px] leading-6 text-[#72726c]">{pendingConversation.title}</p>
            <p className="mt-1 text-[12px] leading-5 text-[#9a9a94]">删除后无法恢复，但不会修改法规知识库和运行日志。</p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPendingDeleteId(null)}
                className="rounded-full border border-[#d8d8d2] px-4 py-2 text-[13px] text-[#555550] transition-colors hover:bg-[#eeeeeb]"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  onDeleteConversation(pendingConversation.id);
                  setPendingDeleteId(null);
                }}
                className="rounded-full bg-[#b64c42] px-4 py-2 text-[13px] font-medium text-white transition-colors hover:bg-[#9f4037]"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function formatConversationTime(timestamp: number) {
  const date = new Date(timestamp);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  }
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
}

function NewChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h5m3 5v5a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V8" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
      <path d="M12 3h4v4M11 8l5-5" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <circle cx="4" cy="10" r="1.25" /><circle cx="10" cy="10" r="1.25" /><circle cx="16" cy="10" r="1.25" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4.5 6h11M8 3.5h4M6 6l.6 9.2a1.5 1.5 0 0 0 1.5 1.3h3.8a1.5 1.5 0 0 0 1.5-1.3L14 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
