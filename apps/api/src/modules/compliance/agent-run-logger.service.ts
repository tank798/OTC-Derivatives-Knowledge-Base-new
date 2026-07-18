import { Injectable } from "@nestjs/common";
import { appendFileSync, existsSync, mkdirSync, readdirSync, statSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";

type LogValue = string | number | boolean | null | undefined | LogValue[] | { [key: string]: LogValue };

@Injectable()
export class AgentRunLoggerService {
  private readonly logsDir: string;
  private readonly mode: "off" | "metadata" | "full";
  private readonly retentionDays: number;

  constructor() {
    const configuredMode = process.env.AGENT_LOG_MODE?.toLowerCase();
    this.mode = configuredMode === "off" || configuredMode === "full" ? configuredMode : "metadata";
    this.retentionDays = Math.max(1, Number(process.env.AGENT_LOG_RETENTION_DAYS ?? 7) || 7);
    this.logsDir = resolve(this.findRepoRoot(), "data/index/eval/logs");
    if (this.mode !== "off") {
      mkdirSync(this.logsDir, { recursive: true });
      this.removeExpiredLogs();
    }
  }

  write(runId: string, sessionId: string, event: string, data: Record<string, LogValue> = {}) {
    if (this.mode === "off") return;
    const timestamp = new Date().toISOString();
    const safeData = this.sanitize(data) as Record<string, LogValue>;
    const record = { timestamp, runId, sessionId, event, data: safeData };

    try {
      appendFileSync(
        resolve(this.logsDir, "agent-runs.jsonl"),
        `${JSON.stringify(record)}\n`,
        "utf8",
      );
      appendFileSync(
        resolve(this.logsDir, `${runId}.md`),
        this.toMarkdown(timestamp, event, safeData),
        "utf8",
      );
    } catch (error) {
      console.warn(`[AgentRunLogger] 无法写入运行日志: ${error instanceof Error ? error.message : error}`);
    }
  }

  private toMarkdown(timestamp: string, event: string, data: Record<string, LogValue>) {
    const title = event.replaceAll("_", " ");
    return [
      `## ${timestamp} · ${title}`,
      "",
      "```json",
      JSON.stringify(data, null, 2),
      "```",
      "",
    ].join("\n");
  }

  private sanitize(value: LogValue, key = ""): LogValue {
    if (/api.?key|authorization|token|secret|password/i.test(key)) return "[REDACTED]";
    if (
      this.mode === "metadata"
      && /^(?:message|content|conclusion|reasoningSummary|quoteExact|explanation|query|purpose|searchedQueries|answerSummary|evidenceContext)$/i.test(key)
    ) {
      return "[OMITTED_BY_LOG_POLICY]";
    }
    if (Array.isArray(value)) return value.map((item) => this.sanitize(item));
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value).map(([childKey, childValue]) => [childKey, this.sanitize(childValue, childKey)]),
      );
    }
    return value;
  }

  private removeExpiredLogs() {
    const cutoff = Date.now() - this.retentionDays * 24 * 60 * 60 * 1000;
    for (const name of readdirSync(this.logsDir)) {
      if (!/\.(?:jsonl|md)$/i.test(name)) continue;
      const path = resolve(this.logsDir, name);
      try {
        if (statSync(path).mtimeMs < cutoff) unlinkSync(path);
      } catch (error) {
        console.warn(`[AgentRunLogger] 无法清理过期日志 ${name}: ${error instanceof Error ? error.message : error}`);
      }
    }
  }

  private findRepoRoot() {
    let current = process.cwd();
    for (let depth = 0; depth < 12; depth += 1) {
      if (existsSync(resolve(current, "data/index/manifest.json"))) return current;
      const parent = resolve(current, "..");
      if (parent === current) break;
      current = parent;
    }
    throw new Error("Cannot find project root containing data/index/manifest.json");
  }
}
