"use client";

import { useState } from "react";
import type { ComplianceQueryResponseData } from "@otc/shared";

type Props = {
  data: ComplianceQueryResponseData;
  sourcesSelected: boolean;
  onShowSources: () => void;
};

export function ComplianceAnswerCard({ data, sourcesSelected, onShowSources }: Props) {
  const answer = data.answer;
  const [copied, setCopied] = useState(false);
  if (!answer) return null;

  const copyAnswer = async () => {
    const text = [
      answer.conclusion,
      "",
      `分析如下：${answer.reasoningSummary}`,
      "",
      "法规依据",
      ...answer.regulatoryBasis.map((basis, index) => [
        `${index + 1}. 《${basis.title}》${basis.articleNo ? ` ${basis.articleNo}` : ""}`,
        basis.documentNumber || "",
        `原文：${basis.quoteExact}`,
        `说明：${basis.explanation}`,
        basis.url || "",
      ].filter(Boolean).join("\n")),
      ...(answer.missingInformation.length ? ["", "当前仍缺少", ...answer.missingInformation.map((item) => `- ${item}`)] : []),
      ...(answer.manualReviewNote ? ["", "复核提示", answer.manualReviewNote] : []),
    ].join("\n");

    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard can be unavailable in local non-secure contexts.
    }
  };

  return (
    <article className="w-full max-w-[740px] animate-slide-up text-[#30302d]">
      <section className="border-b border-[#deded9] pb-6">
        <div className="flex items-start justify-between gap-5">
          <div className="min-w-0">
            <p className="text-[16px] font-semibold leading-8 tracking-[-0.01em] text-[#242421]">{answer.conclusion}</p>
            <p className="mt-3 whitespace-pre-wrap text-[14px] leading-7 text-[#4c4c47]">
              <span className="font-medium text-[#343431]">分析如下：</span>
              {answer.reasoningSummary}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {answer.regulatoryBasis.length > 0 && (
              <button
                type="button"
                onClick={onShowSources}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] transition-colors ${
                  sourcesSelected
                    ? "border-[#c8c8c2] bg-[#ecece8] text-[#373733]"
                    : "border-[#d8d8d2] bg-white text-[#686863] hover:bg-[#f0f0ed] hover:text-[#292926]"
                }`}
              >
                <SourcesPanelIcon />
                法规依据 {answer.regulatoryBasis.length}
              </button>
            )}
            <button
              type="button"
              onClick={copyAnswer}
              className="rounded-full border border-[#d8d8d2] bg-white px-3 py-1.5 text-[11px] text-[#686863] transition-colors hover:bg-[#f0f0ed] hover:text-[#292926]"
            >
              {copied ? "已复制" : "复制"}
            </button>
          </div>
        </div>
      </section>

      {answer.missingInformation.length > 0 && (
        <section className="border-b border-[#deded9] py-6">
          <SectionHeading>当前仍缺少</SectionHeading>
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[13px] leading-6 text-[#65655f]">
            {answer.missingInformation.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ul>
        </section>
      )}

      {answer.manualReviewNote && (
        <section className="py-6">
          <SectionHeading>复核提示</SectionHeading>
          <p className="mt-3 whitespace-pre-wrap text-[13px] leading-6 text-[#65655f]">{answer.manualReviewNote}</p>
        </section>
      )}
    </article>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-[11px] font-medium tracking-[0.08em] text-[#8f8f89]">{children}</h3>;
}

function SourcesPanelIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.35" />
      <path d="M12.5 4v12" stroke="currentColor" strokeWidth="1.35" />
    </svg>
  );
}
