"use client";

import { useEffect, useState } from "react";
import type { AgentRegulatoryAnswer, RetrievalHit } from "@otc/shared";
import { groupRegulatorySources, type RegulatorySourceDocument } from "../lib/regulatory-sources";

type Props = {
  open: boolean;
  answer?: AgentRegulatoryAnswer;
  hits: RetrievalHit[];
  onClose: () => void;
};

export function RegulatorySourcesPanel({ open, answer, hits, onClose }: Props) {
  const sourceDocuments = groupRegulatorySources(answer, hits);
  const wikiEntries = answer?.wikiBasis ?? [];
  const [expandedKey, setExpandedKey] = useState<string | null>(sourceDocuments[0]?.key ?? null);
  const [activeTab, setActiveTab] = useState<"regulations" | "wiki">("regulations");

  useEffect(() => {
    setExpandedKey(sourceDocuments[0]?.key ?? null);
    setActiveTab(sourceDocuments.length ? "regulations" : "wiki");
  }, [answer, hits]);

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
            <h2 className="text-[14px] font-semibold text-[#2d2d29]">参考依据</h2>
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

        <div className="flex shrink-0 gap-1 border-b border-[#e4e4df] px-3 py-2">
          <button
            type="button"
            onClick={() => setActiveTab("regulations")}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${activeTab === "regulations" ? "bg-[#e9e9e5] text-[#30302d]" : "text-[#85857f] hover:bg-[#f0f0ed]"}`}
          >
            法规原文 {sourceDocuments.length || ""}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("wiki")}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${activeTab === "wiki" ? "bg-[#e9e9e5] text-[#30302d]" : "text-[#85857f] hover:bg-[#f0f0ed]"}`}
          >
            专家 Wiki {wikiEntries.length || ""}
          </button>
        </div>

        <div className="scrollbar-hidden flex-1 overflow-y-auto px-3 py-4">
          {activeTab === "regulations" && sourceDocuments.length ? (
            <div className="space-y-2.5">
              {sourceDocuments.map((document, index) => (
                <SourceCard
                  key={document.key}
                  document={document}
                  index={index}
                  expanded={expandedKey === document.key}
                  onToggle={() => setExpandedKey((current) => current === document.key ? null : document.key)}
                />
              ))}
            </div>
          ) : activeTab === "wiki" && wikiEntries.length ? (
            <div className="space-y-2.5">
              {wikiEntries.map((entry, index) => <WikiCard key={entry.id} entry={entry} index={index} />)}
            </div>
          ) : (
            <div className="flex min-h-[55vh] flex-col items-center justify-center px-8 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#deded9] bg-white text-[#898983]">
                <SourcesIcon />
              </div>
              <p className="mt-4 text-[13px] font-medium text-[#5e5e58]">
                {activeTab === "regulations" ? "当前没有法规依据" : "当前没有使用专家 Wiki"}
              </p>
              <p className="mt-1.5 text-[11px] leading-5 text-[#9b9b95]">
                {activeTab === "regulations"
                  ? "完成法规问答后，模型实际引用的法规原文会集中显示在这里。"
                  : "只有回答实际使用的业务 Know-how 才会显示；Wiki 不能替代法规原文。"}
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

function WikiCard({ entry, index }: { entry: NonNullable<AgentRegulatoryAnswer["wikiBasis"]>[number]; index: number }) {
  return (
    <article className="rounded-2xl border border-[#dfdfda] bg-white px-3.5 py-3.5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-md bg-[#eeeeeb] text-[10px] font-medium text-[#6e6e68]">{index + 1}</span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[13px] font-medium leading-5 text-[#30302d]">{entry.title}</h3>
          <p className="mt-1 text-[10px] text-[#969690]">{entry.status === "reviewed" ? "已由专家复核" : "用户已确认，待专家复核"}</p>
        </div>
      </div>
      <p className="mt-3 whitespace-pre-wrap break-words text-[12px] leading-6 text-[#454541]">{entry.content}</p>
      {entry.scope && <p className="mt-3 text-[11px] leading-5 text-[#777771]">适用范围：{entry.scope}</p>}
      {!!entry.tags.length && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {entry.tags.map((tag) => <span key={tag} className="rounded-md bg-[#f1f1ee] px-2 py-1 text-[10px] text-[#72726c]">{tag}</span>)}
        </div>
      )}
    </article>
  );
}

function SourceCard({
  document,
  index,
  expanded,
  onToggle,
}: {
  document: RegulatorySourceDocument;
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
        <span className="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-md bg-[#eeeeeb] text-[10px] font-medium text-[#6e6e68]">{index + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium leading-5 text-[#30302d]">《{document.title}》</span>
          <span className="mt-1 block truncate text-[10px] text-[#969690]">
            {[`${document.chunks.length} 个引用`, document.documentNumber].filter(Boolean).join(" · ")}
          </span>
        </span>
        <ChevronIcon expanded={expanded} />
      </button>

      {expanded && (
        <div className="border-t border-[#ecece8] px-3.5 pb-4 pt-3">
          {(document.publisher || document.status) && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {document.publisher && <span className="rounded-md bg-[#f1f1ee] px-2 py-1 text-[10px] text-[#72726c]">{document.publisher}</span>}
              {document.status && <span className="rounded-md bg-[#f1f1ee] px-2 py-1 text-[10px] text-[#72726c]">{document.status}</span>}
            </div>
          )}
          <div className="space-y-4">
            {document.chunks.map((chunk, chunkIndex) => (
              <section
                key={chunk.evidenceId}
                className={chunkIndex ? "border-t border-[#ecece8] pt-4" : ""}
              >
                {chunk.articleLabel && (
                  <p className="mb-2 text-[10px] font-medium tracking-[0.06em] text-[#8f8f89]">{chunk.articleLabel}</p>
                )}
                <div className="break-words whitespace-pre-wrap text-[12px] leading-6 text-[#454541]">
                  {chunk.text}
                </div>
                {!chunk.hasCompleteChunk && (
                  <p className="mt-2 text-[10px] leading-4 text-[#a06850]">该历史记录未保存完整引用原文，仅能显示当时的逐字引文。</p>
                )}
              </section>
            ))}
          </div>
          {document.url && (
            <a
              href={document.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-[#4d6482] transition-colors hover:text-[#2d496e] hover:underline"
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
      <path d="M12.5 4v12" stroke="currentColor" strokeWidth="1.35" />
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
