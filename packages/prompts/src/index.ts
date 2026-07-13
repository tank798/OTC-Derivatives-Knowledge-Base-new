export const promptManifest = {
  agent: {
    planner: "agent/retrieval-planner.md",
    answer: "agent/evidence-answer.md",
    reviewer: "agent/answer-reviewer.md",
  },
} as const;

export type PromptKey = keyof typeof promptManifest.agent;
