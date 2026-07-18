import { Injectable } from "@nestjs/common";
import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { wikiEntrySchema, type WikiEntry, type WikiProposal } from "@otc/shared";

type SaveWikiInput = {
  proposal: WikiProposal;
  sourceSessionId: string;
  sourceQuestion: string;
};

/**
 * 本地专家 Wiki。
 *
 * JSONL 是程序读取的唯一结构化来源；Markdown 是面向人的只读生成视图。
 * Wiki 条目只代表经用户确认的业务 Know-how，不会被当成法规原文。
 */
@Injectable()
export class WikiService {
  private readonly jsonlPath: string;
  private readonly markdownPath: string;
  private entries: WikiEntry[] = [];

  constructor() {
    const repoRoot = this.findRepoRoot();
    this.jsonlPath = resolve(repoRoot, "wiki/entries.jsonl");
    this.markdownPath = resolve(repoRoot, "wiki/专家知识Wiki.md");
    mkdirSync(dirname(this.jsonlPath), { recursive: true });
    this.entries = this.loadEntries();
    this.writeHumanReadableWiki();
  }

  list() {
    return [...this.entries].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  }

  getByIds(ids: string[]) {
    const wanted = new Set(ids);
    return this.entries.filter((entry) => wanted.has(entry.id));
  }

  search(query: string, limit = 4) {
    const queryTokens = this.tokens(query);
    if (!queryTokens.size) return [];

    return this.entries
      .map((entry) => ({ entry, score: this.scoreEntry(entry, queryTokens) }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score || right.entry.updatedAt.localeCompare(left.entry.updatedAt))
      .slice(0, limit)
      .map((item) => item.entry);
  }

  save({ proposal, sourceSessionId, sourceQuestion }: SaveWikiInput) {
    const now = new Date().toISOString();
    const normalizedContent = this.normalize(proposal.content);
    const existing = this.entries.find((entry) => this.normalize(entry.content) === normalizedContent);
    if (existing) return { entry: existing, created: false };

    const entry: WikiEntry = {
      id: `wiki_${randomUUID().replaceAll("-", "").slice(0, 16)}`,
      title: proposal.title.trim(),
      content: proposal.content.trim(),
      scope: proposal.scope.trim(),
      tags: [...new Set(proposal.tags.map((tag) => tag.trim()).filter(Boolean))].slice(0, 12),
      status: "user_confirmed",
      createdAt: now,
      updatedAt: now,
      sourceSessionId,
      sourceQuestion,
    };

    this.entries.push(entry);
    this.persist();
    return { entry, created: true };
  }

  private loadEntries() {
    if (!existsSync(this.jsonlPath)) return [];
    const parsed: WikiEntry[] = [];
    for (const line of readFileSync(this.jsonlPath, "utf8").split(/\r?\n/u)) {
      if (!line.trim()) continue;
      try {
        const result = wikiEntrySchema.safeParse(JSON.parse(line));
        if (result.success) parsed.push(result.data);
      } catch {
        // Keep startup resilient: one malformed local line must not break QA.
      }
    }
    return parsed;
  }

  private persist() {
    const body = this.entries.map((entry) => JSON.stringify(entry)).join("\n");
    this.atomicWrite(this.jsonlPath, body ? `${body}\n` : "");
    this.writeHumanReadableWiki();
  }

  private writeHumanReadableWiki() {
    const sections = this.list().map((entry) => [
      `## ${entry.title}`,
      "",
      entry.content,
      "",
      `- 适用范围：${entry.scope || "待补充"}`,
      `- 标签：${entry.tags.length ? entry.tags.join("、") : "无"}`,
      `- 状态：${entry.status === "reviewed" ? "已复核" : "用户已确认，待专家复核"}`,
      `- 更新时间：${entry.updatedAt}`,
      `- 条目ID：${entry.id}`,
    ].join("\n"));

    const body = [
      "# 专家知识 Wiki",
      "",
      "> 本文件保存业务人员确认的术语解释、实践经验和适用边界。它不是监管法规原文；回答中的确定性法律结论仍必须由法规 Chunk 支持。",
      "",
      sections.length ? sections.join("\n\n---\n\n") : "当前暂无条目。可在问答中纠正回答，确认后由系统写入。",
      "",
    ].join("\n");
    this.atomicWrite(this.markdownPath, body);
  }

  private scoreEntry(entry: WikiEntry, queryTokens: Set<string>) {
    const titleTokens = this.tokens(entry.title);
    const bodyTokens = this.tokens([entry.content, entry.scope, entry.tags.join(" ")].join(" "));
    let score = 0;
    for (const token of queryTokens) {
      if (titleTokens.has(token)) score += 3;
      if (bodyTokens.has(token)) score += 1;
    }
    return score / Math.sqrt(Math.max(1, queryTokens.size));
  }

  private tokens(value: string) {
    const normalized = this.normalize(value);
    const tokens = new Set<string>();
    for (const match of normalized.matchAll(/[a-z0-9.%]+/gu)) tokens.add(match[0]);
    const chinese = [...normalized].filter((character) => /[\u3400-\u9fff]/u.test(character));
    for (let index = 0; index < chinese.length; index += 1) {
      tokens.add(chinese[index]);
      if (index + 1 < chinese.length) tokens.add(`${chinese[index]}${chinese[index + 1]}`);
      if (index + 2 < chinese.length) tokens.add(`${chinese[index]}${chinese[index + 1]}${chinese[index + 2]}`);
    }
    return tokens;
  }

  private normalize(value: string) {
    return value.normalize("NFKC").toLowerCase().replace(/\s+/gu, "").trim();
  }

  private atomicWrite(path: string, content: string) {
    const temporary = `${path}.tmp`;
    writeFileSync(temporary, content, "utf8");
    renameSync(temporary, path);
  }

  private findRepoRoot() {
    let current = process.cwd();
    for (let depth = 0; depth < 8; depth += 1) {
      if (existsSync(resolve(current, "pnpm-workspace.yaml"))) return current;
      const parent = dirname(current);
      if (parent === current) break;
      current = parent;
    }
    throw new Error("无法定位项目根目录，Wiki 未初始化");
  }
}
