"use client";

import { useEffect, useMemo, useState } from "react";
import type { AgentProgressEvent } from "@otc/shared";

type Props = {
  progress?: AgentProgressEvent[];
  active: boolean;
};

export function ThinkingBubble({ progress = [], active }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [expanded, setExpanded] = useState(active);

  useEffect(() => {
    if (!active) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  const steps = useMemo(() => progress.length ? progress : [{
    id: "connecting",
    label: "正在连接法规 Agent",
    status: "running" as const,
  }], [progress]);
  const completedCount = steps.filter((step) => step.status === "done").length;
  const activeStep = [...steps].reverse().find((step) => step.status === "running");

  if (!active && !progress.length) return null;

  return (
    <div className="mb-3 w-full animate-fade-in text-[13px] text-[#6f6f6b]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="group flex items-center gap-2 rounded-lg py-1 text-left transition-colors hover:text-[#252522]"
        aria-expanded={expanded}
      >
        {active ? (
          <span className="agent-breath-dot" aria-hidden="true" />
        ) : (
          <CheckIcon />
        )}
        <span className={active ? "agent-thinking-label font-medium" : "font-medium"}>
          {active
            ? activeStep?.label ?? "正在处理"
            : `已完成 ${completedCount} 个处理步骤`}
        </span>
        {active && elapsed > 2 && <span className="tabular-nums text-[#a0a09a]">{elapsed}s</span>}
        <ChevronIcon expanded={expanded} />
      </button>

      {expanded && (
        <div className="ml-[7px] mt-2 border-l border-[#deded9] pl-5">
          <div className="space-y-3 py-1.5">
            {steps.map((step) => (
              <div key={step.id} className="relative flex min-h-5 items-start justify-between gap-4">
                <span
                  className={`absolute -left-[23px] top-[6px] h-[5px] w-[5px] rounded-full ${
                    step.status === "running" ? "agent-step-dot bg-[#1d1d1b]" : "bg-[#b7b7b1]"
                  }`}
                />
                <span className={step.status === "running" ? "font-medium text-[#282825]" : "text-[#85857f]"}>
                  {step.label}
                </span>
                {step.detail && <span className="shrink-0 text-[11px] text-[#aaa9a2]">{step.detail}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="m5 10 3.1 3.1L15.5 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 20 20"
      fill="none"
      className={`ml-0.5 text-[#aaa9a2] transition-transform ${expanded ? "rotate-180" : ""}`}
      aria-hidden="true"
    >
      <path d="m5.5 7.5 4.5 4.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
