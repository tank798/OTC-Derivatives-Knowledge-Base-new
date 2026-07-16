"use client";

import { useState } from "react";
import type { ComplianceQueryResponseData } from "@otc/shared";
import { groupRegulatorySources } from "../lib/regulatory-sources";

type Props = {
  data: ComplianceQueryResponseData;
};

type ActionsProps = Props & {
  sourcesSelected: boolean;
  onShowSources: () => void;
};

const ANSWER_BODY_CLASS = "whitespace-pre-wrap text-[15px] leading-7 text-[#4c4c47]";

export function ComplianceAnswerCard({ data }: Props) {
  const answer = data.answer;
  if (!answer) return null;

  return (
    <article className="w-full max-w-[740px] animate-slide-up text-[#30302d]">
      <section className="border-b border-[#deded9] pb-6">
        <p className="text-[17px] font-semibold leading-8 tracking-[-0.01em] text-[#242421]">{answer.conclusion}</p>
        <p className={`mt-3 ${ANSWER_BODY_CLASS}`}>
          <span className="font-medium text-[#343431]">分析如下：</span>
          {answer.reasoningSummary}
        </p>
      </section>

    </article>
  );
}

export function ComplianceAnswerActions({ data, sourcesSelected, onShowSources }: ActionsProps) {
  const answer = data.answer;
  const [copied, setCopied] = useState(false);
  if (!answer) return null;
  const referencedDocumentCount = groupRegulatorySources(answer, data.hits).length;

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
    <>
      {answer.regulatoryBasis.length > 0 && (
        <button
          type="button"
          onClick={onShowSources}
          className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] transition-colors ${
            sourcesSelected
              ? "border-[#c8c8c2] bg-[#ecece8] text-[#373733]"
              : "border-[#d8d8d2] bg-white text-[#686863] hover:bg-[#f0f0ed] hover:text-[#292926]"
          }`}
        >
          <SourcesPanelIcon />
          法规依据 {referencedDocumentCount}
        </button>
      )}
      <button
        type="button"
        onClick={copyAnswer}
        className="rounded-full border border-[#d8d8d2] bg-white px-3 py-1.5 text-[12px] text-[#686863] transition-colors hover:bg-[#f0f0ed] hover:text-[#292926]"
      >
        {copied ? "已复制" : "复制"}
      </button>
    </>
  );
}

function SourcesPanelIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.35" />
      <path d="M12.5 4v12" stroke="currentColor" strokeWidth="1.35" />
    </svg>
  );
}
