import { Injectable } from "@nestjs/common";
import { existsSync, readFileSync } from "fs";
import { resolve } from "path";
import { promptManifest, type PromptKey } from "@otc/prompts";

@Injectable()
export class PromptService {
  private readonly cache = new Map<string, string>();
  private readonly promptsDir: string;

  constructor() {
    const repoRoot = this.findRepoRoot();
    this.promptsDir = resolve(repoRoot, "packages/prompts");
    for (const relativePath of Object.values(promptManifest.agent)) {
      this.loadPrompt(relativePath);
    }
  }

  getAgentPrompt(key: PromptKey): string { return this.loadPrompt(promptManifest.agent[key]); }

  getAgentPromptPath(key: PromptKey): string { return promptManifest.agent[key]; }

  private loadPrompt(relativePath: string): string {
    const cached = this.cache.get(relativePath);
    if (cached) return cached;

    const fullPath = resolve(this.promptsDir, relativePath);
    const content = readFileSync(fullPath, "utf-8").trim();
    if (!content) throw new Error(`Agent prompt is empty: ${fullPath}`);
    this.cache.set(relativePath, content);
    return content;
  }

  private findRepoRoot(): string {
    const candidates = [process.cwd(), __dirname];

    for (const start of candidates) {
      let dir = start;
      for (let i = 0; i < 12; i++) {
        const promptPath = resolve(
          dir,
          "packages/prompts",
          promptManifest.agent.questionRewrite,
        );
        if (existsSync(promptPath)) return dir;

        const parent = resolve(dir, "..");
        if (parent === dir) break;
        dir = parent;
      }
    }

    throw new Error("Cannot find repo root: packages/prompts not found");
  }
}
