"use client";

import { useState } from "react";

type Props = {
  feedback?: "helpful" | "badcase";
  onHelpful: () => void;
  onBadcase: (note: string) => void;
};

export function AnswerFeedback({ feedback, onHelpful, onBadcase }: Props) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");

  if (feedback === "helpful") {
    return <p className="mt-4 text-[12px] text-[#85857f]">已标记为有帮助</p>;
  }

  if (feedback === "badcase" && !editing) {
    return (
      <div className="mt-4 flex items-center gap-2 text-[12px] text-[#85857f]">
        <span>已加入 Badcase</span>
        <button type="button" onClick={() => setEditing(true)} className="rounded-full px-2 py-1 hover:bg-[#ecece8] hover:text-[#343430]">
          补充说明
        </button>
      </div>
    );
  }

  if (editing) {
    return (
      <div className="mt-5 rounded-2xl border border-[#deded9] bg-white p-3.5">
        <label htmlFor="badcase-note" className="text-[13px] font-medium text-[#3b3b37]">
          这条回答哪里需要改进？
        </label>
        <textarea
          id="badcase-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          autoFocus
          rows={3}
          placeholder="例如：遗漏了适用主体，或引用的条款不能支持结论……"
          className="mt-2 w-full resize-none rounded-xl bg-[#f4f4f1] px-3 py-2.5 text-[13px] leading-6 text-[#343430] outline-none placeholder:text-[#a2a29c] focus:ring-1 focus:ring-[#c8c8c2]"
        />
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={() => setEditing(false)} className="rounded-full px-3 py-1.5 text-[12px] text-[#73736d] hover:bg-[#eeeeeb]">
            取消
          </button>
          <button
            type="button"
            onClick={() => {
              onBadcase(note.trim());
              setEditing(false);
            }}
            className="rounded-full bg-[#292926] px-3.5 py-1.5 text-[12px] font-medium text-white hover:bg-black"
          >
            加入 Badcase
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 flex items-center gap-2">
      <span className="text-[12px] text-[#969690]">这条回答有帮助吗？</span>
      <button
        type="button"
        onClick={onHelpful}
        className="flex h-7 w-7 items-center justify-center rounded-full text-[#777771] transition-colors hover:bg-[#e9e9e5] hover:text-[#2f2f2b]"
        aria-label="这条回答有帮助"
        title="有帮助"
      >
        <ThumbUpIcon />
      </button>
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="flex h-7 w-7 items-center justify-center rounded-full text-[#777771] transition-colors hover:bg-[#e9e9e5] hover:text-[#2f2f2b]"
        aria-label="这条回答需要改进"
        title="需要改进"
      >
        <ThumbDownIcon />
      </button>
    </div>
  );
}

function ThumbUpIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M7.5 8.2 10.4 3c.5-.9 1.8-.5 1.8.5v3h3a1.8 1.8 0 0 1 1.7 2.3l-1.5 5.3a2 2 0 0 1-1.9 1.4h-6m0-7.3v7.3H4.8a1.5 1.5 0 0 1-1.5-1.5V9.7a1.5 1.5 0 0 1 1.5-1.5h2.7Z" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ThumbDownIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="m7.5 11.8 2.9 5.2c.5.9 1.8.5 1.8-.5v-3h3a1.8 1.8 0 0 0 1.7-2.3l-1.5-5.3a2 2 0 0 0-1.9-1.4h-6m0 7.3V4.5H4.8A1.5 1.5 0 0 0 3.3 6v4.3a1.5 1.5 0 0 0 1.5 1.5h2.7Z" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
