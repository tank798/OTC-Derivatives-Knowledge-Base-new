import { Injectable } from "@nestjs/common";
import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

type LogValue = string | number | boolean | null | undefined | LogValue[] | { [key: string]: LogValue };

@Injectable()
export class AgentRunLoggerService {
  private readonly logsDir: string;

  constructor() {
    this.logsDir = resolve(this.findRepoRoot(), "data/index/eval/logs");
    mkdirSync(this.logsDir, { recursive: true });
  }

  write(runId: string, sessionId: string, event: string, data: Record<string, LogValue> = {}) {
    const timestamp = new Date().toISOString();
    const safeData = this.redact(data) as Record<string, LogValue>;
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

  private redact(value: LogValue, key = ""): LogValue {
    if (/api.?key|authorization|token|secret|password/i.test(key)) return "[REDACTED]";
    if (Array.isArray(value)) return value.map((item) => this.redact(item));
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value).map(([childKey, childValue]) => [childKey, this.redact(childValue, childKey)]),
      );
    }
    return value;
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
