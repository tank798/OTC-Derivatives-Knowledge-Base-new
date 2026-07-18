"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { AgentProgressEvent } from "@otc/shared";

type Props = {
  progress?: AgentProgressEvent[];
  active: boolean;
  actions?: ReactNode;
};

export function ThinkingBubble({ progress = [], active, actions }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [expanded, setExpanded] = useState(active);

  useEffect(() => {
    if (!active) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    const startedAt = Date.now();
    setElapsed(0);
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  const steps = useMemo(() => progress.length ? progress : [{
    id: "connecting",
    label: "正在连接法规 Agent",
    status: "running" as const,
  }], [progress]);
  if (!active && !progress.length) return null;

  return (
    <div className="mb-3 w-full animate-fade-in text-[14px] text-[#6f6f6b]">
      <div className="flex min-h-9 items-center justify-between gap-3">
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
            {active ? "正在进行中" : "已完成"}
          </span>
          {active && elapsed > 2 && <span className="tabular-nums text-[#a0a09a]">{formatElapsedTime(elapsed)}</span>}
          <ChevronIcon expanded={expanded} />
        </button>
        {!active && actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
      </div>

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
                <span className={step.status === "running" ? "agent-thinking-label font-medium" : "text-[#85857f]"}>
                  {step.label}
                </span>
                {step.detail && <span className="shrink-0 text-[12px] text-[#aaa9a2]">{step.detail}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatElapsedTime(totalSeconds: number) {
  if (totalSeconds < 60) return `${totalSeconds}s`;

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const paddedSeconds = String(seconds).padStart(2, "0");

  if (hours < 1) return `${minutes}m ${paddedSeconds}s`;
  return `${hours}h ${String(minutes).padStart(2, "0")}m ${paddedSeconds}s`;
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
