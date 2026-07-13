#!/usr/bin/env node

import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EVAL_DIR = resolve(ROOT, "data/index/eval");
const QUERY_PATH = resolve(EVAL_DIR, "queries.jsonl");
const apiRequire = createRequire(resolve(ROOT, "apps/api/package.json"));

const { ConfigService } = apiRequire("@nestjs/config");
const { QueryAnalysisService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/query-analysis/query-analysis.service.js"));
const { RetrievalService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/retrieval/retrieval.service.js"));
const { ContextBuilderService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/context-builder/context-builder.service.js"));
const { CitationValidatorService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/citation-validator/citation-validator.service.js"));
const { PromptService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/prompt/prompt.service.js"));
const { LlmService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/llm/llm.service.js"));
const { ComplianceService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/compliance/compliance.service.js"));
const { AgentWorkflowService } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/compliance/agent-workflow.service.js"));
const { HybridRegulationSearchTool } = apiRequire(resolve(ROOT, "apps/api/dist/apps/api/src/modules/compliance/hybrid-regulation-search.tool.js"));

function readJsonl(path) {
  return readFileSync(path, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function evaluateCase(testCase, result) {
  const answer = result.answer;
  const issues = [];
  if (answer.directAnswer !== testCase.expected_direct_answer) {
    issues.push(`直接回答应为“${testCase.expected_direct_answer}”，实际为“${answer.directAnswer}”`);
  }
  if (!answer.citationValidation?.passed) {
    issues.push(`引用校验未通过：${answer.citationValidation?.issues?.join("；") || "未知原因"}`);
  }
  if (!answer.reviewValidation?.passed) issues.push("独立审查模型未通过回答");
  if (!result.agentTrace || result.agentTrace.retrievalRounds > 2 || result.agentTrace.repairCount > 1 || result.agentTrace.reviewCount > 2) {
    issues.push("受控智能体次数记录缺失或超过上限");
  }
  const hitMap = new Map(result.hits.map((hit) => [hit.id, hit]));
  for (const basis of answer.regulatoryBasis) {
    const evidence = hitMap.get(basis.evidenceId);
    if (!evidence) issues.push(`最终引用 ${basis.evidenceId} 不在实际检索结果中`);
    else {
      if (!evidence.text.includes(basis.quoteExact || basis.excerpt)) issues.push(`引文不是 ${basis.evidenceId} 的连续逐字原文`);
      if (basis.url !== evidence.url) issues.push(`《${basis.title}》的链接不是正式元数据 URL`);
    }
  }
  if (/雪球/.test(testCase.query)) {
    const planText = JSON.stringify(result.retrievalPlan ?? {});
    if (!/敲入/.test(planText) || !/敲出/.test(planText)) issues.push("雪球检索计划未包含敲入、敲出正式术语");
    if (!/场外期权|收益凭证/.test(planText)) issues.push("雪球检索计划未结合问题中的法规产品术语");
  }
  const citedTitles = answer.regulatoryBasis.map((basis) => basis.title);
  for (const required of testCase.required_citation_titles ?? []) {
    if (!citedTitles.some((title) => title.includes(required))) issues.push(`最终答案未引用《${required}》`);
  }
  for (const alternatives of testCase.required_citation_title_groups ?? []) {
    if (!alternatives.some((required) => citedTitles.some((title) => title.includes(required)))) {
      issues.push(`最终答案未引用以下任一等价依据：${alternatives.map((title) => `《${title}》`).join("、")}`);
    }
  }
  const evaluatedText = [
    answer.directAnswer,
    answer.conclusion,
    ...answer.restrictions,
    ...(answer.scope?.conditions ?? []),
    ...answer.missingInfo,
  ].join("\n");
  for (const pattern of testCase.required_answer_patterns ?? []) {
    if (!new RegExp(pattern).test(evaluatedText)) issues.push(`最终答案缺少必要内容：/${pattern}/`);
  }
  for (const pattern of testCase.forbidden_answer_patterns ?? []) {
    if (new RegExp(pattern).test(answer.conclusion)) issues.push(`最终答案出现禁止表述：/${pattern}/`);
  }
  const missingUrls = answer.regulatoryBasis.filter((basis) => !/^https?:\/\//.test(basis.url));
  if (missingUrls.length) issues.push(`有${missingUrls.length}条最终法规依据缺少官网链接`);
  return { passed: issues.length === 0, issues };
}

function withoutRepeatedDecision(answer) {
  return answer.conclusion.replace(new RegExp(`^${answer.directAnswer}[，,。；;：:\\s]+`), "").trim();
}

async function main() {
  const cases = readJsonl(QUERY_PATH);
  if (!cases.length) throw new Error("评测集为空");
  if (!process.env.LLM_API_KEY) throw new Error("端到端评测必须配置 LLM_API_KEY，不能退化为只检索评测");

  const analyzer = new QueryAnalysisService();
  const retrieval = new RetrievalService();
  await retrieval.onModuleInit();
  const contextBuilder = new ContextBuilderService();
  const validator = new CitationValidatorService();
  const llm = new LlmService(new ConfigService(process.env));
  const prompts = new PromptService();
  const searchTool = new HybridRegulationSearchTool(retrieval);
  const workflow = new AgentWorkflowService(llm, analyzer, contextBuilder, validator, prompts, searchTool);
  const service = new ComplianceService(workflow);

  const results = [];
  for (const testCase of cases) {
    const response = await service.answer(testCase.query, { debug: true });
    const evaluation = evaluateCase(testCase, response);
    results.push({
      id: testCase.id,
      query: testCase.query,
      passed: evaluation.passed,
      issues: evaluation.issues,
      expected_direct_answer: testCase.expected_direct_answer,
      answer: response.answer,
      query_analysis: response.queryAnalysis,
      retrieval_plan: response.retrievalPlan,
      evidence_assessment: response.evidenceAssessment,
      review_result: response.reviewResult,
      agent_trace: response.agentTrace,
      model_context: response.hits.map((hit, index) => ({
        context_order: index + 1,
        chunk_id: hit.chunkId,
        title: hit.title,
        article: hit.articleEnd && hit.articleEnd !== hit.articleNo ? `${hit.articleNo}至${hit.articleEnd}` : hit.articleNo,
        official_url: hit.url,
        retrieval_methods: hit.retrievalMethods,
      })),
    });
  }

  const passedCount = results.filter((row) => row.passed).length;
  const output = {
    generated_at: new Date().toISOString(),
    evaluation_type: "production_end_to_end_qa",
    pipeline: "AgentWorkflowService → planner LLM → hybrid_regulation_search → evidence assessment LLM → answer LLM → deterministic validation → independent reviewer LLM",
    model: llm.modelName,
    corpus: retrieval.stats,
    summary: { total: results.length, passed: passedCount, failed: results.length - passedCount },
    results,
  };
  mkdirSync(EVAL_DIR, { recursive: true });
  writeFileSync(resolve(EVAL_DIR, "results.json"), JSON.stringify(output, null, 2) + "\n", "utf8");
  const lines = [
    "# 端到端问答评测结果", "",
    `- 链路：${output.pipeline}`,
    `- 模型：${output.model}`,
    `- 语料：${output.corpus.documents} 份法规 / ${output.corpus.chunks} 个 Chunk`,
    `- 结果：${passedCount}/${results.length} 通过`, "",
    "| 问题 | 直接回答 | 检索轮次 | LLM调用 | 程序校验 | 独立审查 | 结果 |",
    "|---|---|---:|---:|---|---|---|",
    ...results.map((row) => `| ${row.query} | ${row.answer.directAnswer} | ${row.agent_trace.retrievalRounds} | ${row.agent_trace.llmCalls} | ${row.answer.citationValidation?.passed ? "PASS" : "FAIL"} | ${row.answer.reviewValidation?.passed ? "PASS" : "FAIL"} | ${row.passed ? "PASS" : "FAIL"} |`),
    "",
    ...results.flatMap((row) => [
      `## ${row.query}`, "",
      `**${row.answer.directAnswer}。** ${withoutRepeatedDecision(row.answer)}`, "",
      `检索轮次：${row.agent_trace.retrievalRounds}；模型调用：${row.agent_trace.llmCalls}；独立审查：${row.answer.reviewValidation?.verdict ?? "未完成"}。`, "",
      "依据：", "",
      ...(row.answer.regulatoryBasis.length ? row.answer.regulatoryBasis.map((basis) => `- [《${basis.title}》${basis.articleNo ? `（${basis.articleNo}）` : ""}](${basis.url})：${basis.requirement}`) : ["- 无"]),
      "",
      ...(row.issues.length ? ["问题：", "", ...row.issues.map((issue) => `- ${issue}`), ""] : []),
    ]),
  ];
  writeFileSync(resolve(EVAL_DIR, "results.md"), lines.join("\n"), "utf8");
  console.log(JSON.stringify(output.summary, null, 2));
  if (passedCount !== results.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
