export const promptManifest = {
  agent: {
    questionRewrite: "agent/question-rewrite.md",
    retrieval: "agent/retrieval.md",
    evidenceAnswer: "agent/evidence-answer.md",
    citationRepair: "agent/citation-repair.md",
  },
} as const;

export type PromptKey = keyof typeof promptManifest.agent;
