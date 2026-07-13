"use client";

import { useEffect, useState } from "react";
import type { AgentRegulatoryAnswer, AgentRegulatoryBasis } from "@otc/shared";

type Props = {
  open: boolean;
  answer?: AgentRegulatoryAnswer;
  onClose: () => void;
};

export function RegulatorySourcesPanel({ open, answer, onClose }: Props) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(0);

  useEffect(() => {
    setExpandedIndex(answer?.regulatoryBasis.length ? 0 : null);
  }, [answer]);

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="关闭法规依据"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/15 backdrop-blur-[1px] xl:hidden"
        />
      )}
      <aside
        aria-hidden={!open}
        className={`fixed inset-y-0 right-0 z-40 flex w-[min(400px,92vw)] flex-col border-l border-[#deded9] bg-[#fbfbfa] shadow-[-16px_0_50px_rgba(32,32,28,0.08)] transition-transform duration-200 xl:static xl:z-auto xl:w-[390px] xl:shrink-0 xl:shadow-none ${
          open ? "translate-x-0" : "translate-x-full xl:hidden"
        }`}
      >
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#e4e4df] px-4">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold text-[#2d2d29]">法规依据</h2>
            <p className="mt-0.5 text-[9px] text-[#9a9a94]">
              {answer?.regulatoryBasis.length ? `${answer.regulatoryBasis.length} 条已引用法规` : "等待当前回答引用法规"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#777771] transition-colors hover:bg-[#ecece8] hover:text-[#2d2d29]"
            aria-label="隐藏法规依据"
            title="隐藏法规依据"
          >
            <ClosePanelIcon />
          </button>
        </header>

        <div className="scrollbar-hidden flex-1 overflow-y-auto px-3 py-4">
          {answer?.regulatoryBasis.length ? (
            <div className="space-y-2.5">
              {answer.regulatoryBasis.map((basis, index) => (
                <SourceCard
                  key={`${basis.evidenceId}-${index}`}
                  basis={basis}
                  index={index}
                  expanded={expandedIndex === index}
                  onToggle={() => setExpandedIndex((current) => current === index ? null : index)}
                />
              ))}
            </div>
          ) : (
            <div className="flex min-h-[55vh] flex-col items-center justify-center px-8 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#deded9] bg-white text-[#898983]">
                <SourcesIcon />
              </div>
              <p className="mt-4 text-[12px] font-medium text-[#5e5e58]">当前没有法规依据</p>
              <p className="mt-1.5 text-[10px] leading-5 text-[#9b9b95]">完成法规问答后，模型实际引用的条文会集中显示在这里。</p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

function SourceCard({
  basis,
  index,
  expanded,
  onToggle,
}: {
  basis: AgentRegulatoryBasis;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <article className="overflow-hidden rounded-2xl border border-[#dfdfda] bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-3.5 py-3.5 text-left transition-colors hover:bg-[#fafaf8]"
      >
        <span className="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-md bg-[#eeeeeb] text-[9px] font-medium text-[#6e6e68]">{index + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[12px] font-medium leading-5 text-[#30302d]">《{basis.title}》</span>
          <span className="mt-1 block truncate text-[9px] text-[#969690]">
            {[basis.articleNo, basis.documentNumber].filter(Boolean).join(" · ") || basis.publisher}
          </span>
        </span>
        <ChevronIcon expanded={expanded} />
      </button>

      {expanded && (
        <div className="border-t border-[#ecece8] px-3.5 pb-4 pt-3">
          {(basis.publisher || basis.status) && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {basis.publisher && <span className="rounded-md bg-[#f1f1ee] px-2 py-1 text-[9px] text-[#72726c]">{basis.publisher}</span>}
              {basis.status && <span className="rounded-md bg-[#f1f1ee] px-2 py-1 text-[9px] text-[#72726c]">{basis.status}</span>}
            </div>
          )}
          <p className="mb-1.5 text-[9px] font-medium tracking-[0.06em] text-[#999993]">原文</p>
          <blockquote className="whitespace-pre-wrap border-l-2 border-[#c9c9c3] pl-3 text-[11px] leading-6 text-[#575752]">{basis.quoteExact}</blockquote>
          <p className="mt-3 text-[11px] leading-5 text-[#3f3f3a]">{basis.explanation}</p>
          {basis.url && (
            <a
              href={basis.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1 text-[10px] font-medium text-[#4d6482] transition-colors hover:text-[#2d496e] hover:underline"
            >
              查看官网原文 <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
      )}
    </article>
  );
}

function ClosePanelIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.35" />
      <path d="M12.5 4v12M8.5 7 6 10l2.5 3" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className={`mt-1 shrink-0 text-[#999993] transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden="true">
      <path d="m5.5 7.5 4.5 4.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SourcesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M5 3.5h7.5A2.5 2.5 0 0 1 15 6v10.5H7.5A2.5 2.5 0 0 1 5 14V3.5Z" stroke="currentColor" strokeWidth="1.35" />
      <path d="M5 14a2.5 2.5 0 0 1 2.5-2.5H15M8 6.5h4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" />
    </svg>
  );
}
