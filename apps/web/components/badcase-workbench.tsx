"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { BadcaseRecord } from "./chat-types";

type Props = {
  records: BadcaseRecord[];
  onResolve: (id: string) => void;
  onReopen: (id: string) => void;
  onDelete: (id: string) => void;
};

export function BadcaseWorkbench({ records, onResolve, onReopen, onDelete }: Props) {
  const [filter, setFilter] = useState<"open" | "resolved" | "all">("open");
  const visible = useMemo(
    () => [...records]
      .filter((record) => filter === "all" || record.status === filter)
      .sort((left, right) => right.createdAt - left.createdAt),
    [filter, records],
  );

  return (
    <section className="scrollbar-hidden h-full overflow-y-auto px-5 pb-12 pt-8 sm:px-10">
      <div className="mx-auto max-w-[920px]">
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#deded9] pb-6">
          <div>
            <p className="text-[12px] font-medium tracking-[0.08em] text-[#969690]">内部复核</p>
            <h1 className="mt-1 text-[26px] font-semibold tracking-[-0.035em] text-[#242421]">Badcase 工作台</h1>
            <p className="mt-2 text-[13px] leading-6 text-[#777771]">集中查看用户认为需要改进的回答，用于发现通用检索、证据和表达问题。</p>
          </div>
          <div className="flex rounded-full bg-[#eaeae6] p-1">
            {([
              ["open", "待复核"],
              ["resolved", "已复核"],
              ["all", "全部"],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded-full px-3.5 py-1.5 text-[12px] transition-colors ${
                  filter === value ? "bg-white font-medium text-[#30302d] shadow-sm" : "text-[#777771] hover:text-[#30302d]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {visible.length ? (
          <div className="mt-6 overflow-hidden rounded-[22px] border border-[#deded9] bg-white shadow-[0_3px_18px_rgba(39,39,35,0.035)]">
            {visible.map((record, index) => (
              <article key={record.id} className="border-b border-[#e5e5e1] p-5 last:border-b-0 sm:p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-7 min-w-7 shrink-0 items-center justify-center rounded-lg bg-[#ededeb] px-1.5 text-[11px] font-semibold tabular-nums text-[#6f6f69]">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <p className="text-[13px] font-semibold text-[#343430]">Badcase</p>
                      <p className="mt-0.5 text-[11px] text-[#969690]">{formatTime(record.createdAt)}</p>
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${
                    record.status === "open" ? "bg-[#fff0e6] text-[#9b5c30]" : "bg-[#e8f2e9] text-[#4f7553]"
                  }`}>
                    {record.status === "open" ? "待复核" : "已复核"}
                  </span>
                </div>

                <div className="mt-5 divide-y divide-[#ecece8] border-y border-[#ecece8]">
                  <BadcaseSection label="问题">
                    <p className="whitespace-pre-wrap text-[15px] font-medium leading-7 text-[#292926]">{record.question}</p>
                    {record.note && (
                      <div className="mt-3 rounded-xl bg-[#f2f2ef] px-3.5 py-3">
                        <p className="text-[11px] font-medium text-[#8a8a84]">需要改进的地方</p>
                        <p className="mt-1 whitespace-pre-wrap text-[13px] leading-6 text-[#4b4b46]">{record.note}</p>
                      </div>
                    )}
                  </BadcaseSection>

                  <BadcaseSection label="回答">
                    <p className="whitespace-pre-wrap text-[13px] leading-7 text-[#4f4f4a]">{record.answer}</p>
                  </BadcaseSection>

                  <BadcaseSection label="参考依据">
                    {record.references.length ? (
                      <div className="space-y-3">
                        {record.references.map((reference, referenceIndex) => (
                          <div key={`${reference.kind}-${reference.title}-${referenceIndex}`} className="rounded-xl border border-[#e2e2de] bg-[#fafaf8] px-3.5 py-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-[13px] font-semibold leading-6 text-[#383834]">
                                  {reference.kind === "regulation" ? `《${reference.title}》` : reference.title}
                                </p>
                                {reference.locator && <p className="mt-0.5 text-[11px] leading-5 text-[#92928c]">{reference.locator}</p>}
                              </div>
                              <span className="shrink-0 rounded-md bg-[#ecece8] px-2 py-1 text-[10px] text-[#72726c]">
                                {reference.kind === "regulation" ? "法规" : "Wiki"}
                              </span>
                            </div>
                            {reference.quote && (
                              <blockquote className="mt-3 border-l-2 border-[#d3d3cd] pl-3 text-[12px] leading-6 text-[#5b5b56]">
                                {reference.quote}
                              </blockquote>
                            )}
                            {reference.explanation && (
                              <p className="mt-2 text-[11px] leading-5 text-[#888882]">{reference.explanation}</p>
                            )}
                            {reference.url && (
                              <a href={reference.url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[11px] font-medium text-[#536b85] hover:underline">
                                查看官网原文 ↗
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[12px] text-[#969690]">这条回答没有保存可追溯的法规或Wiki依据。</p>
                    )}
                  </BadcaseSection>
                </div>

                <div className="mt-4 flex justify-end gap-2">
                  <button type="button" onClick={() => onDelete(record.id)} className="rounded-full px-3 py-1.5 text-[12px] text-[#9a5a53] hover:bg-[#fff1ef]">
                    删除
                  </button>
                  {record.status === "open" ? (
                    <button type="button" onClick={() => onResolve(record.id)} className="rounded-full bg-[#292926] px-3.5 py-1.5 text-[12px] font-medium text-white hover:bg-black">
                      标记已复核
                    </button>
                  ) : (
                    <button type="button" onClick={() => onReopen(record.id)} className="rounded-full border border-[#d8d8d2] px-3.5 py-1.5 text-[12px] text-[#60605a] hover:bg-[#eeeeeb]">
                      重新打开
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="flex min-h-[360px] flex-col items-center justify-center text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e9e9e5] text-[#777771]">
              <ReviewIcon />
            </div>
            <p className="mt-4 text-[15px] font-medium text-[#494944]">当前没有{filter === "open" ? "待复核" : filter === "resolved" ? "已复核" : ""} Badcase</p>
            <p className="mt-1 text-[12px] text-[#92928c]">在回答下方选择“需要改进”后，会自动进入这里。</p>
          </div>
        )}
      </div>
    </section>
  );
}

function BadcaseSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="grid gap-2 py-4 sm:grid-cols-[76px_minmax(0,1fr)] sm:gap-4">
      <h3 className="pt-0.5 text-[11px] font-semibold tracking-[0.08em] text-[#92928c]">{label}</h3>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function formatTime(timestamp: number) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

function ReviewIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M5 3.5h8.5A1.5 1.5 0 0 1 15 5v10a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 15V5A1.5 1.5 0 0 1 5 3.5Z" stroke="currentColor" strokeWidth="1.4" />
      <path d="m6.5 10 1.7 1.7 4.2-4.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
