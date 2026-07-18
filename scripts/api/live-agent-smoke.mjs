#!/usr/bin/env node

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");

function parseArgs(argv) {
  const options = {
    baseUrl: "http://127.0.0.1:4000/api",
    queries: "data/index/eval/general_queries.jsonl",
    ids: new Set(),
    limit: Infinity,
    concurrency: 1,
    output: "data/index/eval/live-results/latest.json",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--base-url") options.baseUrl = argv[++index];
    else if (value === "--queries") options.queries = argv[++index];
    else if (value === "--ids") options.ids = new Set((argv[++index] ?? "").split(",").filter(Boolean));
    else if (value === "--limit") options.limit = Number(argv[++index] ?? 1);
    else if (value === "--concurrency") options.concurrency = Math.max(1, Number(argv[++index] ?? 1));
    else if (value === "--output") options.output = argv[++index];
    else throw new Error(`未知参数: ${value}`);
  }
  return options;
}

function readQueries(path) {
  return readFileSync(resolve(root, path), "utf8")
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function postQuery(baseUrl, message, sessionId) {
  const startedAt = Date.now();
  const response = await fetch(`${baseUrl}/compliance/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, ...(sessionId ? { sessionId } : {}), debug: true }),
    signal: AbortSignal.timeout(180_000),
  });
  const body = await response.json();
  if (!response.ok || !body.success) {
    throw new Error(`${response.status} ${body?.error?.code ?? ""} ${body?.error?.message ?? "请求失败"}`.trim());
  }
  return { data: body.data, latencyMs: Date.now() - startedAt };
}

async function runCase(testCase, baseUrl) {
  const turns = [];
  let message = testCase.query;
  let sessionId;
  let response;

  for (let turn = 0; turn < 5; turn += 1) {
    const result = await postQuery(baseUrl, message, sessionId);
    response = result.data;
    sessionId = response.sessionId;
    turns.push({ message, stage: response.stage, latencyMs: result.latencyMs, proposedQuery: response.proposedQuery ?? "" });
    if (response.stage === "complete") break;
    if (response.stage === "awaiting_confirmation") message = testCase.confirmationReply ?? "是";
    else if (response.stage === "awaiting_clarification") {
      if (!testCase.clarificationReply) throw new Error(`需要澄清但用例未提供 clarificationReply：${response.message}`);
      message = testCase.clarificationReply;
    } else if (response.stage === "awaiting_wiki_confirmation") message = "不写入 Wiki";
    else throw new Error(`未知对话阶段: ${response.stage}`);
  }

  if (!response || response.stage !== "complete" || !response.answer) {
    throw new Error("未在有界轮次内得到法规回答");
  }

  const hitIds = new Set(response.hits.map((hit) => hit.id));
  const invalidEvidenceIds = response.answer.regulatoryBasis
    .map((basis) => basis.evidenceId)
    .filter((id) => !hitIds.has(id));

  return {
    id: testCase.id,
    query: testCase.query,
    ok: response.answer.citationValidation.passed && invalidEvidenceIds.length === 0,
    turns,
    conclusion: response.answer.conclusion,
    citedRegulations: [...new Set(response.answer.regulatoryBasis.map((basis) => basis.title))],
    citedChunkCount: response.answer.regulatoryBasis.length,
    wikiCount: response.answer.wikiBasis.length,
    invalidEvidenceIds,
    trace: response.trace ?? null,
  };
}

async function pool(items, concurrency, worker) {
  const results = new Array(items.length);
  let cursor = 0;
  async function next() {
    while (cursor < items.length) {
      const index = cursor++;
      try {
        results[index] = await worker(items[index]);
      } catch (error) {
        results[index] = { id: items[index].id, query: items[index].query, ok: false, error: error instanceof Error ? error.message : String(error) };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => next()));
  return results;
}

const options = parseArgs(process.argv.slice(2));
let queries = readQueries(options.queries);
if (options.ids.size) queries = queries.filter((item) => options.ids.has(item.id));
queries = queries.slice(0, options.limit);
if (!queries.length) throw new Error("没有选中任何真实链路用例");

const startedAt = new Date().toISOString();
const results = await pool(queries, options.concurrency, (item) => runCase(item, options.baseUrl));
const report = {
  startedAt,
  finishedAt: new Date().toISOString(),
  verificationScope: "workflow_and_citation_integrity",
  qualityJudgement: "not_included",
  baseUrl: options.baseUrl,
  queryFile: options.queries,
  total: results.length,
  passed: results.filter((item) => item.ok).length,
  failed: results.filter((item) => !item.ok).length,
  results,
};

const outputPath = resolve(root, options.output);
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (report.failed) process.exitCode = 1;
