#!/usr/bin/env node

/**
 * 200题法规问答评测器
 *
 * 运行模式：
 *   重新调用 API：
 *     node scripts/eval_200_questions.mjs --fresh --output-dir output/eval_200_questions_iter1
 *   只使用已有答案重判：
 *     node scripts/eval_200_questions.mjs --judge-only \
 *       --input output/eval_200_questions/02_system_answers.jsonl \
 *       --fresh --output-dir output/eval_200_questions_rejudged
 *
 * 评测器把“回答生命周期/结构有效性”和“语义判定”分开记录，避免把未完成回答
 * 当成普通错误，也避免用全局否定词和字面数字匹配污染开放文本评测。
 */

import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
  readdirSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { join, dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = join(__dirname, "..");
const DEFAULT_OUTPUT_DIR = join(PROJECT_ROOT, "output", "eval_200_questions");
const DEFAULT_QUESTION_FILE = join(PROJECT_ROOT, "场外衍生品法规问答题库_200题_20260719.md");

const API_BASE = process.env.API_BASE_URL || "http://127.0.0.1:4000/api";
const QUERY_URL = `${API_BASE}/compliance/query`;
const MAX_INTERACTIONS = 4;
const RETRY_LIMIT = 3;

const CONFIRMATION_STAGES = new Set(["awaiting_confirmation"]);
const INSUFFICIENT_CONCLUSION_RE = /(?:无法|不能|不足|未能|尚无|没有).{0,16}(?:确定|判断|得出|支持|证据|依据|结论)|证据不足/u;

const NEGATIVE_MODAL_PATTERNS = [
  "不可以", "不能", "不得", "严禁", "禁止", "不应", "不可", "无需", "不需要", "不包括", "不是", "否",
];
const POSITIVE_MODAL_PATTERNS = [
  "可以", "能够", "能", "需要", "应当", "必须", "应", "可", "包括", "属于", "是",
];
const NUMERIC_BOUNDARY_PATTERNS = [
  "不低于", "不少于", "不超过", "不高于", "不多于", "不晚于", "不早于", "不迟于", "不小于", "不同",
];

function ensureDir(dir) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

function assertFreshDir(dir) {
  if (!existsSync(dir)) return;
  const entries = readdirSync(dir);
  if (entries.length > 0) {
    throw new Error(`--fresh 要求输出目录为空：${dir}`);
  }
}

function resolveProjectPath(value) {
  if (!value) return null;
  return isAbsolute(value) ? value : resolve(PROJECT_ROOT, value);
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    judgeOnly: false,
    fresh: false,
    overwrite: false,
    outputDir: DEFAULT_OUTPUT_DIR,
    input: null,
    questionFile: DEFAULT_QUESTION_FILE,
    ids: null,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--judge-only") options.judgeOnly = true;
    else if (arg === "--fresh") options.fresh = true;
    else if (arg === "--overwrite") options.overwrite = true;
    else if (arg === "--output-dir") options.outputDir = resolveProjectPath(argv[++i]);
    else if (arg === "--input") options.input = resolveProjectPath(argv[++i]);
    else if (arg === "--question-file") options.questionFile = resolveProjectPath(argv[++i]);
    else if (arg === "--ids") {
      options.ids = new Set((argv[++i] || "").split(",").map((id) => id.trim()).filter(Boolean));
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`未知参数：${arg}（使用 --help 查看用法）`);
    }
  }

  if (options.judgeOnly && !options.input) {
    options.input = join(options.outputDir, "02_system_answers.jsonl");
  }
  return options;
}

function printHelp() {
  console.log(`用法：
  node scripts/eval_200_questions.mjs [--fresh] [--output-dir DIR]
  node scripts/eval_200_questions.mjs --judge-only --input ANSWERS.jsonl --fresh --output-dir DIR

参数：
  --judge-only       只重判已有 02_system_answers.jsonl，不调用 API
  --input FILE       缓存答案 JSONL；默认读取输出目录下的 02_system_answers.jsonl
  --output-dir DIR   本轮独立输出目录，支持相对项目根目录的路径
  --fresh            输出目录必须不存在或为空，防止覆盖上一轮结果
  --overwrite        允许重写指定目录中的评测文件（不建议与 --fresh 同时使用）
  --ids Q001,Q002    只运行/评测指定题目，用于分层抽样
  --question-file    指定题库 Markdown 文件
`);
}

function now() {
  return new Date().toISOString();
}

function sha256File(filePath) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function currentGitCommit() {
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], { cwd: PROJECT_ROOT, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

function writeJsonAtomic(filePath, value) {
  const tempPath = `${filePath}.tmp-${process.pid}`;
  writeFileSync(tempPath, JSON.stringify(value, null, 2), "utf8");
  renameSync(tempPath, filePath);
}

function writeTextAtomic(filePath, value) {
  const tempPath = `${filePath}.tmp-${process.pid}`;
  writeFileSync(tempPath, value, "utf8");
  renameSync(tempPath, filePath);
}

// ─── 题库解析 ───────────────────────────────────────────────
function parseQuestions(filePath) {
  const text = readFileSync(filePath, "utf8");
  const questions = [];
  const lines = text.split("\n");
  let currentId = null;
  let currentQ = null;
  let currentA = null;
  let currentRegulation = null;
  let section = "";
  let mode = "scan";

  const pushCurrent = () => {
    if (currentId && currentQ && currentA) {
      questions.push({
        id: currentId,
        section,
        question: currentQ.trim(),
        answer: currentA.trim(),
        regulation: (currentRegulation || "").trim(),
      });
    }
  };

  for (const line of lines) {
    const sectionMatch = line.match(/^## (.+)/);
    if (sectionMatch) {
      pushCurrent();
      section = sectionMatch[1].trim();
      currentId = null;
      currentQ = null;
      currentA = null;
      currentRegulation = null;
      mode = "scan";
      continue;
    }

    const qMatch = line.match(/^### (Q\d+)/);
    if (qMatch) {
      pushCurrent();
      currentId = qMatch[1];
      currentQ = null;
      currentA = null;
      currentRegulation = null;
      mode = "scan";
      continue;
    }

    if (/^\*\*Q：\*\*/u.test(line)) {
      currentQ = line.replace(/^\*\*Q：\*\*/u, "").trim();
      mode = "q";
      continue;
    }

    if (mode === "q" && currentQ !== null) {
      if (/^\*\*A：\*\*/u.test(line)) {
        currentA = line.replace(/^\*\*A：\*\*/u, "").trim();
        mode = "a";
        continue;
      }
      if (line.trim() && !/^---/.test(line) && !/^\*\*参考/u.test(line)) currentQ += ` ${line.trim()}`;
      continue;
    }

    if (/^\*\*A：\*\*/u.test(line)) {
      currentA = line.replace(/^\*\*A：\*\*/u, "").trim();
      mode = "a";
      continue;
    }

    if (mode === "a" && currentA !== null) {
      if (/^\*\*参考法规/u.test(line)) {
        currentRegulation = line.replace(/^\*\*参考法规：\*\*/u, "").trim();
        pushCurrent();
        currentId = null;
        currentQ = null;
        currentA = null;
        currentRegulation = null;
        mode = "scan";
        continue;
      }
      if (line.trim() && !/^---/.test(line) && !/^\*\*参考页码/u.test(line)) currentA += ` ${line.trim()}`;
    }
  }

  pushCurrent();
  return questions;
}

function selectQuestions(questions, ids) {
  if (!ids || ids.size === 0) return questions;
  const selected = questions.filter((q) => ids.has(q.id));
  const missing = [...ids].filter((id) => !questions.some((q) => q.id === id));
  if (missing.length) throw new Error(`题库中不存在题号：${missing.join(", ")}`);
  return selected;
}

function validateQuestionSet(questions, { ids } = {}) {
  const seen = new Set();
  const duplicates = [];
  for (const q of questions) {
    if (seen.has(q.id)) duplicates.push(q.id);
    seen.add(q.id);
  }
  if (duplicates.length) throw new Error(`题库存在重复题号：${duplicates.join(", ")}`);
  if (!ids && questions.length !== 200) {
    throw new Error(`全量评测要求200题，实际解析到${questions.length}题`);
  }
  if (ids && questions.length !== ids.size) {
    throw new Error(`抽样题目数量不一致：请求${ids.size}题，解析到${questions.length}题`);
  }
}

function readJsonl(filePath) {
  if (!existsSync(filePath)) throw new Error(`找不到输入答案文件：${filePath}`);
  const lines = readFileSync(filePath, "utf8").split("\n").filter((line) => line.trim());
  const records = [];
  for (let i = 0; i < lines.length; i += 1) {
    try {
      records.push(JSON.parse(lines[i]));
    } catch (error) {
      throw new Error(`答案JSONL第${i + 1}行解析失败：${error.message}`);
    }
  }
  return records;
}

function validateAnswerRecords(records, questions, { ids } = {}) {
  const expected = new Set(questions.map((q) => q.id));
  const byId = new Map();
  const duplicates = [];
  for (const record of records) {
    if (!record?.id) continue;
    if (byId.has(record.id)) duplicates.push(record.id);
    byId.set(record.id, record);
  }
  if (duplicates.length) throw new Error(`答案文件存在重复题号：${duplicates.join(", ")}`);
  const missing = [...expected].filter((id) => !byId.has(id));
  if (missing.length) throw new Error(`答案文件缺少题号：${missing.join(", ")}`);
  const unexpected = [...byId.keys()].filter((id) => !expected.has(id));
  if (unexpected.length && !ids) throw new Error(`答案文件包含题库之外的题号：${unexpected.join(", ")}`);
  return questions.map((q) => byId.get(q.id));
}

// ─── API 生命周期 ───────────────────────────────────────────
function getResponseData(payload, label) {
  if (!payload?.success) throw new Error(`${label}错误：${payload?.error?.message || "未知错误"}`);
  if (!payload.data || typeof payload.data !== "object") throw new Error(`${label}缺少data`);
  return payload.data;
}

async function sendQuery(message, sessionId) {
  const response = await fetch(QUERY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sessionId ? { message, sessionId } : { message }),
  });
  if (!response.ok) throw new Error(`API请求失败：${response.status} ${response.statusText}`);
  return getResponseData(await response.json(), "API响应");
}

function responseSnapshot(data) {
  return {
    stage: data.stage || "unknown",
    answer: data.answer || null,
    message: data.message || "",
    hits: Array.isArray(data.hits) ? data.hits : [],
    proposedQuery: data.proposedQuery || "",
  };
}

/**
 * 状态规则：
 * - awaiting_confirmation 才能自动确认问题改写；
 * - awaiting_clarification 必须停止并交给人工，不得机械发送“是”；
 * - awaiting_wiki_confirmation 在基准评测中视为协议异常，不自动写Wiki；
 * - 只有 complete 才能成为语义评测输入。
 */
async function askQuestion(questionText) {
  let data = await sendQuery(questionText);
  const sessionId = data.sessionId;
  const snapshots = [responseSnapshot(data)];

  for (let interaction = 1; interaction <= MAX_INTERACTIONS; interaction += 1) {
    const stage = data.stage;
    if (stage === "complete") {
      return {
        sessionId,
        rewrittenQuery: snapshots[0].proposedQuery || questionText,
        answer: data.answer || null,
        message: data.message || "",
        hits: Array.isArray(data.hits) ? data.hits : [],
        steps: snapshots.length,
        runStatus: "complete",
        snapshots,
      };
    }

    if (stage === "awaiting_clarification") {
      return {
        sessionId,
        rewrittenQuery: snapshots[0].proposedQuery || questionText,
        answer: null,
        message: data.message || "Agent请求补充澄清",
        hits: Array.isArray(data.hits) ? data.hits : [],
        steps: snapshots.length,
        runStatus: "needs_clarification",
        snapshots,
      };
    }

    if (stage === "awaiting_wiki_confirmation") {
      return {
        sessionId,
        rewrittenQuery: snapshots[0].proposedQuery || questionText,
        answer: null,
        message: data.message || "Agent请求Wiki确认",
        hits: Array.isArray(data.hits) ? data.hits : [],
        steps: snapshots.length,
        runStatus: "protocol_error",
        error: "基准评测不自动确认或写入Wiki",
        snapshots,
      };
    }

    if (!CONFIRMATION_STAGES.has(stage)) {
      return {
        sessionId,
        rewrittenQuery: snapshots[0].proposedQuery || questionText,
        answer: data.answer || null,
        message: data.message || "",
        hits: Array.isArray(data.hits) ? data.hits : [],
        steps: snapshots.length,
        runStatus: "protocol_error",
        error: `未处理的Agent阶段：${stage}`,
        snapshots,
      };
    }

    await sleep(300);
    data = await sendQuery("是", sessionId);
    snapshots.push(responseSnapshot(data));

    if (interaction === MAX_INTERACTIONS) {
      return {
        sessionId,
        rewrittenQuery: snapshots[0].proposedQuery || questionText,
        answer: data.answer || null,
        message: data.message || "",
        hits: Array.isArray(data.hits) ? data.hits : [],
        steps: snapshots.length,
        runStatus: "protocol_error",
        error: `超过最大交互轮数${MAX_INTERACTIONS}`,
        snapshots,
      };
    }
  }

  throw new Error("Agent生命周期处理异常");
}

async function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function queryWithRetry(questionText, maxRetries = RETRY_LIMIT) {
  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    try {
      return await askQuestion(questionText);
    } catch (error) {
      console.error(`  尝试 ${attempt}/${maxRetries} 失败：${error.message}`);
      if (attempt === maxRetries) {
        return { runStatus: "api_error", answer: null, error: error.message, steps: 0, hits: [] };
      }
      await sleep(1000 * attempt);
    }
  }
  return { runStatus: "api_error", answer: null, error: "未知API错误", steps: 0, hits: [] };
}

// ─── 答案结构校验 ───────────────────────────────────────────
function extractConclusion(answer) {
  if (!answer) return "";
  if (typeof answer === "string") return answer;
  return typeof answer.conclusion === "string" ? answer.conclusion : "";
}

function isInsufficientConclusion(conclusion) {
  return INSUFFICIENT_CONCLUSION_RE.test(conclusion);
}

function validateAnswerStructure(answer) {
  const reasons = [];
  if (!answer || typeof answer !== "object" || Array.isArray(answer)) {
    return { valid: false, insufficient: false, reasons: ["answer不是对象"] };
  }

  const conclusion = extractConclusion(answer).trim();
  const reasoningSummary = typeof answer.reasoningSummary === "string"
    ? answer.reasoningSummary.trim()
    : (typeof answer.reasoning === "string" ? answer.reasoning.trim() : "");
  const insufficient = isInsufficientConclusion(conclusion);

  if (conclusion.length < 2) reasons.push("conclusion为空或过短");
  if (!reasoningSummary) reasons.push("缺少reasoningSummary");
  if (!Array.isArray(answer.regulatoryBasis)) reasons.push("regulatoryBasis不是数组");
  if (!Array.isArray(answer.wikiBasis)) reasons.push("wikiBasis不是数组");
  if (!answer.citationValidation || typeof answer.citationValidation.passed !== "boolean") {
    reasons.push("缺少citationValidation.passed");
  } else if (answer.citationValidation.passed !== true) {
    reasons.push("citationValidation未通过");
  }

  if (Array.isArray(answer.regulatoryBasis)) {
    answer.regulatoryBasis.forEach((basis, index) => {
      if (!basis || typeof basis !== "object") reasons.push(`regulatoryBasis[${index}]不是对象`);
      else {
        if (typeof basis.evidenceId !== "string" || !basis.evidenceId.trim()) reasons.push(`regulatoryBasis[${index}]缺少evidenceId`);
        if (typeof basis.quoteExact !== "string" || !basis.quoteExact.trim()) reasons.push(`regulatoryBasis[${index}]缺少quoteExact`);
        if (typeof basis.explanation !== "string" || !basis.explanation.trim()) reasons.push(`regulatoryBasis[${index}]缺少explanation`);
      }
    });
    if (!insufficient && answer.regulatoryBasis.length === 0) reasons.push("确定性结论没有法规依据");
  }

  return {
    valid: reasons.length === 0,
    insufficient,
    reasons,
    conclusion,
    reasoningSummary,
  };
}

// ─── 语义归一化 ─────────────────────────────────────────────
function normalizeUnicode(text) {
  return String(text || "")
    .normalize("NFKC")
    .replace(/[\u00a0\u3000]/gu, " ")
    .replace(/[％﹪]/gu, "%")
    .replace(/[，]/gu, ",")
    .replace(/[。]/gu, ".")
    .replace(/[；]/gu, ";")
    .replace(/[：]/gu, ":")
    .replace(/\s+/gu, " ")
    .trim()
    .toLowerCase();
}

function chineseNumberToNumber(raw) {
  const text = String(raw || "").replace(/[两俩]/gu, "二");
  if (!text) return null;
  if (/^\d+(?:\.\d+)?$/u.test(text)) return Number(text);
  if (!/^[零〇一二三四五六七八九十百千万亿点]+$/u.test(text)) return null;
  if (text.includes("点")) {
    const [integer, decimal] = text.split("点");
    const integerValue = chineseNumberToNumber(integer) ?? 0;
    const decimalDigits = [...decimal].map((digit) => ({ 零: "0", 〇: "0", 一: "1", 二: "2", 三: "3", 四: "4", 五: "5", 六: "6", 七: "7", 八: "8", 九: "9" }[digit] || "")).join("");
    return Number(`${integerValue}.${decimalDigits}`);
  }
  const digitMap = { 零: 0, 〇: 0, 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  const smallUnits = { 十: 10, 百: 100, 千: 1000 };
  const bigUnits = { 万: 1e4, 亿: 1e8 };
  let total = 0;
  let section = 0;
  let number = 0;
  for (const char of text) {
    if (Object.hasOwn(digitMap, char)) number = digitMap[char];
    else if (Object.hasOwn(smallUnits, char)) {
      section += (number || 1) * smallUnits[char];
      number = 0;
    } else if (Object.hasOwn(bigUnits, char)) {
      section = (section + number) || 1;
      total += section * bigUnits[char];
      section = 0;
      number = 0;
    }
  }
  return total + section + number;
}

function formatNumber(number) {
  if (!Number.isFinite(number)) return "";
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(8)));
}

function quantityUnit(rawUnit) {
  const unit = String(rawUnit || "");
  if (["%", "百分比", "百分之"].includes(unit)) return "%";
  if (["‰", "千分之"].includes(unit)) return "‰";
  if (["个月", "月"].includes(unit)) return "month";
  if (["交易日", "个交易日"].includes(unit)) return "trading_day";
  if (["工作日", "个工作日"].includes(unit)) return "workday";
  if (unit === "日") return "day";
  if (unit === "年") return "year";
  if (unit === "名") return "person";
  if (unit === "倍") return "multiple";
  if (unit === "万元") return "10^4元";
  if (unit === "亿元") return "10^8元";
  if (unit === "万") return "10^4";
  if (unit === "亿") return "10^8";
  return unit || "number";
}

function detectOperator(prefix) {
  const text = String(prefix || "");
  if (/(?:不低于|不少于|至少|最低|不小于)$/u.test(text)) return ">=";
  if (/(?:不超过|不高于|不多于|至多|最高|上限)$/u.test(text)) return "<=";
  if (/(?:超过|高于|大于)$/u.test(text)) return ">";
  if (/(?:低于|少于|小于)$/u.test(text)) return "<";
  return "=";
}

function extractQuantities(text) {
  const source = normalizeUnicode(text);
  const quantities = [];
  const consumed = [];
  const add = (match, rawNumber, rawUnit, start, end, unitOverride = null) => {
    const number = chineseNumberToNumber(rawNumber.replace(/[,，]/gu, ""));
    if (number === null) return;
    const unit = quantityUnit(unitOverride || rawUnit);
    const prefix = source.slice(Math.max(0, start - 8), start);
    quantities.push({ value: number, unit, operator: detectOperator(prefix), raw: match });
    consumed.push([start, end]);
  };

  const percentWordRe = /百分之\s*([零〇一二两三四五六七八九十百千万亿点\d.]+)/gu;
  for (const match of source.matchAll(percentWordRe)) {
    add(match[0], match[1], "%", match.index, match.index + match[0].length, "%");
  }
  const perMilleWordRe = /千分之\s*([零〇一二两三四五六七八九十百千万亿点\d.]+)/gu;
  for (const match of source.matchAll(perMilleWordRe)) {
    add(match[0], match[1], "‰", match.index, match.index + match[0].length, "‰");
  }

  const quantityRe = /((?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万亿点]+)\s*(?:%|‰|万元|亿元|万|亿|个月|月|个工作日|工作日|个交易日|交易日|日|年|名|倍))/gu;
  for (const match of source.matchAll(quantityRe)) {
    const full = match[0].replace(/\s+/gu, "");
    const numberMatch = full.match(/^([\d.零〇一二两三四五六七八九十百千万亿点]+)(%|‰|万元|亿元|万|亿|个月|月|个工作日|工作日|个交易日|交易日|日|年|名|倍)$/u);
    if (numberMatch) add(full, numberMatch[1], numberMatch[2], match.index, match.index + match[0].length);
  }
  return quantities;
}

function operatorsCompatible(expected, actual) {
  if (expected === "=" || actual === "=") return true;
  return expected === actual;
}

function compareQuantities(ground, conclusion) {
  const expected = extractQuantities(ground);
  if (expected.length === 0) return { matched: true, expected: [], actual: [], matchedCount: 0, total: 0 };
  const actual = extractQuantities(conclusion);
  const matched = expected.filter((quantity) => actual.some((candidate) => (
    candidate.value === quantity.value
    && candidate.unit === quantity.unit
    && operatorsCompatible(quantity.operator, candidate.operator)
  )));
  return {
    matched: matched.length === expected.length,
    expected,
    actual,
    matchedCount: matched.length,
    total: expected.length,
  };
}

function canonicalizeModals(text) {
  let result = normalizeUnicode(text);
  // 先处理长词，避免“不需要”先被“需要”截断。
  result = result.replace(/不需要|无需|不包括|不可以|不能|不得|严禁|禁止|不应|不可|不是|否/gu, "[否定]");
  result = result.replace(/必须|应当|需要/gu, "[义务]");
  result = result.replace(/可以|能够/gu, "[许可]");
  result = result.replace(/包括|属于/gu, "[包含]");
  result = result.replace(/(^|[^\p{L}])能(?=[与否开展进行申请设置办理])/gu, "$1[许可]");
  return result.replace(/[\s,.;:!?、，。；：？！“”‘’"'（）()《》【】\[\]{}]/gu, "");
}

function normalizeComparableText(text) {
  let result = canonicalizeModals(text);
  result = result.replace(/百分之\s*([零〇一二两三四五六七八九十百千万亿点\d.]+)/gu, (_, number) => `${formatNumber(chineseNumberToNumber(number))}%`);
  result = result.replace(/千分之\s*([零〇一二两三四五六七八九十百千万亿点\d.]+)/gu, (_, number) => `${formatNumber(chineseNumberToNumber(number))}‰`);
  result = result.replace(/([零〇一二两三四五六七八九十百千万亿点]+)\s*(个月|月|个工作日|工作日|个交易日|交易日|日|年|名|倍|%|‰)/gu, (_, number, unit) => `${formatNumber(chineseNumberToNumber(number))}${unit}`);
  return result;
}

function extractKeyPhrases(text) {
  const cleaned = String(text || "")
    .replace(/[，。；、:：,.;；\n]/gu, "|")
    .replace(/\|+/gu, "|")
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length >= 2);
  const seen = new Set();
  return cleaned.filter((part) => {
    const key = normalizeComparableText(part);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function getBigrams(text) {
  const value = String(text || "");
  const bigrams = [];
  for (let i = 0; i < value.length - 1; i += 1) bigrams.push(value.slice(i, i + 2));
  return bigrams;
}

function findPolarityToken(text) {
  const source = normalizeUnicode(text).slice(0, 140);
  const masked = source.replace(new RegExp(NUMERIC_BOUNDARY_PATTERNS.join("|"), "gu"), "边界");
  const patterns = [
    ...NEGATIVE_MODAL_PATTERNS.map((word) => ({ word, polarity: "negative" })),
    ...POSITIVE_MODAL_PATTERNS.map((word) => ({ word, polarity: "positive" })),
  ].sort((a, b) => b.word.length - a.word.length);
  let found = null;
  for (const pattern of patterns) {
    const index = masked.indexOf(pattern.word);
    if (index >= 0 && (!found || index < found.index || (index === found.index && pattern.word.length > found.word.length))) {
      const previous = masked[index - 1] || "";
      if ((pattern.word === "应" && previous === "对")
        || (pattern.word === "可" && previous === "不")
        || (pattern.word === "能" && previous === "功")) continue;
      found = { ...pattern, index };
    }
  }
  return found;
}

function classifyQuestion(question, groundTruth) {
  const q = normalizeUnicode(question);
  const ground = normalizeUnicode(groundTruth);
  const hasBinary = /(?:是否|能否|可否|可不可以|可以吗|能吗|需要吗|应否|是不是|属于.*吗|包括.*吗)/u.test(q);
  const hasEnumeration = /(?:哪些|哪几|列举|分别|什么类型|哪些类型)/u.test(q);
  const numeric = extractQuantities(ground).length > 0 || /(?:多少|比例|百分比|期限|几天|几个月|几年|多长)/u.test(q);
  if (hasBinary && hasEnumeration) return "compound";
  if (hasBinary) return numeric ? "binary_numeric" : "binary";
  if (hasEnumeration) return "enumeration";
  if (numeric) return "numeric";
  return "open";
}

function splitSentences(text) {
  return String(text || "")
    .split(/[。！？!?；;\n]+/u)
    .map((part) => part.trim())
    .filter(Boolean);
}

function stripEnumerationPrefix(text) {
  return String(text || "")
    .replace(/^(?:包括|主要包括|可分为|分为|分别为|分别包括|有|涉及)\s*/u, "")
    .trim();
}

function extractEnumerationPhrases(text) {
  const phrases = [];
  for (const raw of extractKeyPhrases(text)) {
    let phrase = stripEnumerationPrefix(raw)
      .replace(/^证券公司应根据具体情况设置/u, "")
      .replace(/(?:等确定|等因素|等类型)$/u, "")
      .trim();
    if (!phrase || /^(?:这些类型|并非|不是|现行规则|该条)/u.test(phrase)) continue;
    const pieces = phrase.split(/(?:以及|及|和)/u).map((piece) => piece.trim()).filter((piece) => piece.length >= 2);
    phrases.push(...(pieces.length > 1 ? pieces : [phrase]));
  }
  return phrases;
}

function expectedFacts(groundTruth, questionType) {
  const sentences = splitSentences(groundTruth);
  const first = sentences[0] || groundTruth;
  if (questionType === "binary" || questionType === "binary_numeric") {
    return extractKeyPhrases(first);
  }
  if (questionType === "numeric") {
    const facts = [...extractKeyPhrases(first)];
    for (const sentence of sentences.slice(1)) {
      if (extractQuantities(sentence).length > 0 || /(?:除外|不纳入|不含|例外|但书)/u.test(sentence)) {
        facts.push(...extractKeyPhrases(sentence));
      }
    }
    return [...new Set(facts.map((fact) => normalizeComparableText(fact)))].map((normalized) => normalized);
  }
  if (questionType === "enumeration") {
    return extractEnumerationPhrases(first);
  }
  if (questionType === "compound") {
    const facts = extractKeyPhrases(first);
    for (const sentence of sentences.slice(1)) facts.push(...extractEnumerationPhrases(sentence));
    return [...new Set(facts.map((fact) => normalizeComparableText(fact)))].map((normalized) => normalized);
  }
  // 开放式“如何规定”问题以首句核心规则为主，后续解释不再被错误地当成额外必答短语。
  return extractKeyPhrases(first);
}

function phraseMatches(phrase, conclusion) {
  const expected = normalizeComparableText(phrase)
    .replace(/^(?:并|且|应当|应|需要|需)+/u, "");
  const actual = normalizeComparableText(conclusion);
  if (!expected) return true;
  if (actual.includes(expected)) return true;
  const quantityComparison = compareQuantities(phrase, conclusion);
  if (quantityComparison.total > 0 && quantityComparison.matched) return true;
  const expectedWithoutModal = expected.replace(/^(?:否定|许可|义务|包含)/u, "");
  if (expectedWithoutModal && actual.includes(expectedWithoutModal)) return true;
  const expectedBigrams = getBigrams(expected);
  const actualBigrams = getBigrams(actual);
  if (expectedBigrams.length === 0) return false;
  const overlap = expectedBigrams.filter((bigram) => actualBigrams.includes(bigram));
  return overlap.length >= Math.max(1, expectedBigrams.length * 0.65);
}

function judgeAnswer(systemAnswer, groundTruth, question = "") {
  const conclusion = extractConclusion(systemAnswer).trim();
  const ground = String(groundTruth || "").trim();
  const structure = validateAnswerStructure(systemAnswer);
  if (!structure.valid) {
    return {
      verdict: "无效回答",
      structureStatus: "invalid",
      detail: structure.reasons.join("；"),
      structureReasons: structure.reasons,
      questionType: classifyQuestion(question, ground),
    };
  }

  const questionType = classifyQuestion(question, ground);
  const groundKeyPhrases = expectedFacts(ground, questionType);
  const matched = groundKeyPhrases.filter((phrase) => phraseMatches(phrase, conclusion));
  const coverage = groundKeyPhrases.length > 0 ? matched.length / groundKeyPhrases.length : 1;
  const groundPolarity = findPolarityToken(splitSentences(ground)[0] || ground);
  const conclusionPolarity = findPolarityToken(conclusion);
  const polarityMatch = !groundPolarity || !conclusionPolarity
    ? null
    : groundPolarity.polarity === conclusionPolarity.polarity;
  const quantityMatch = compareQuantities(groundKeyPhrases.join("；"), conclusion);

  let adjustedCoverage = coverage;
  if (quantityMatch.total > 0 && !quantityMatch.matched) {
    adjustedCoverage = Math.min(adjustedCoverage, quantityMatch.matchedCount / quantityMatch.total);
  }
  if (questionType === "numeric" && quantityMatch.total > 0 && quantityMatch.matched && adjustedCoverage < 0.5 && groundKeyPhrases.length <= 2) {
    adjustedCoverage = 0.5;
  }
  if (questionType === "numeric" && quantityMatch.total > 0 && quantityMatch.matched && adjustedCoverage < 0.5 && groundKeyPhrases.length === 3) {
    adjustedCoverage = 0.5;
  }

  let verdict;
  let detail;
  const polaritySensitive = questionType === "binary" || questionType === "binary_numeric" || questionType === "compound";
  if (polaritySensitive && polarityMatch === false) {
    verdict = adjustedCoverage >= 0.5 ? "部分正确" : "错误";
    detail = `直接回答极性不一致（标准${groundPolarity.word}，系统${conclusionPolarity.word}），覆盖${matched.length}/${groundKeyPhrases.length}`;
  } else if (questionType === "binary" && polarityMatch === true && adjustedCoverage >= 0.5) {
    verdict = "正确";
    detail = `直接回答极性一致，核心要素覆盖${matched.length}/${groundKeyPhrases.length}`;
  } else if (adjustedCoverage >= 0.8 && (!polaritySensitive || polarityMatch !== false)) {
    verdict = "正确";
    detail = `核心要素覆盖${matched.length}/${groundKeyPhrases.length}`;
  } else if (adjustedCoverage >= 0.5 && (!polaritySensitive || polarityMatch !== false)) {
    verdict = "部分正确";
    const missing = groundKeyPhrases.filter((phrase) => !phraseMatches(phrase, conclusion));
    detail = `部分覆盖${matched.length}/${groundKeyPhrases.length}，缺失：${missing.join("、") || "数值或关键条件"}`;
  } else {
    verdict = "错误";
    detail = `覆盖不足${matched.length}/${groundKeyPhrases.length}`;
  }

  return {
    verdict,
    structureStatus: "valid",
    detail,
    coverage: adjustedCoverage,
    rawCoverage: coverage,
    polarityMatch,
    groundPolarity: groundPolarity?.polarity || null,
    conclusionPolarity: conclusionPolarity?.polarity || null,
    quantityMatch: {
      matched: quantityMatch.matched,
      matchedCount: quantityMatch.matchedCount,
      total: quantityMatch.total,
      expected: quantityMatch.expected,
      actual: quantityMatch.actual,
    },
    questionType,
    groundKeyPhrases,
    matchedCount: matched.length,
    totalPhrases: groundKeyPhrases.length,
  };
}

// ─── 评测结果和报告 ─────────────────────────────────────────
function answerRecordFromResult(question, result, elapsedSeconds) {
  const answer = result.answer || null;
  return {
    id: question.id,
    section: question.section,
    question: question.question,
    groundTruth: question.answer,
    groundRegulation: question.regulation,
    systemAnswer: answer,
    systemConclusion: extractConclusion(answer),
    rewrittenQuery: result.rewrittenQuery || question.question,
    sessionId: result.sessionId || null,
    steps: result.steps || 0,
    elapsedSeconds,
    runStatus: result.runStatus || (answer ? "complete" : "api_error"),
    lifecycleMessage: result.message || "",
    lifecycleError: result.error || "",
    snapshots: result.snapshots || [],
    hits: result.hits || [],
    timestamp: now(),
  };
}

function buildJudgment(record, question) {
  if (record.runStatus === "needs_clarification") {
    return {
      id: question.id,
      section: question.section,
      question: question.question,
      groundTruth: question.answer,
      verdict: "需要澄清",
      structureStatus: "not_completed",
      detail: record.lifecycleMessage || "Agent请求澄清，未形成完整回答",
      runStatus: record.runStatus,
    };
  }
  if (record.runStatus === "protocol_error") {
    return {
      id: question.id,
      section: question.section,
      question: question.question,
      groundTruth: question.answer,
      verdict: "协议错误",
      structureStatus: "not_completed",
      detail: record.lifecycleError || record.lifecycleMessage || "Agent生命周期未按协议完成",
      runStatus: record.runStatus,
    };
  }
  if (record.runStatus === "api_error" || record.error) {
    return {
      id: question.id,
      section: question.section,
      question: question.question,
      groundTruth: question.answer,
      verdict: "API失败",
      structureStatus: "not_completed",
      detail: `API调用失败：${record.error || record.lifecycleError || "未知错误"}`,
      runStatus: "api_error",
    };
  }

  const judgment = judgeAnswer(record.systemAnswer, question.answer, question.question);
  return {
    id: question.id,
    section: question.section,
    question: question.question,
    groundTruth: question.answer,
    systemConclusion: record.systemConclusion || extractConclusion(record.systemAnswer),
    runStatus: record.runStatus || "complete",
    ...judgment,
  };
}

function countVerdicts(results) {
  return results.reduce((counts, result) => {
    counts[result.verdict] = (counts[result.verdict] || 0) + 1;
    return counts;
  }, {});
}

function buildReport(evalResults, options, sourcePath) {
  const counts = countVerdicts(evalResults);
  const total = evalResults.length;
  const pct = (value) => (total ? ((value / total) * 100).toFixed(1) : "0.0");
  const semanticTotal = (counts["正确"] || 0) + (counts["部分正确"] || 0) + (counts["错误"] || 0);
  const completed = (counts["正确"] || 0) + (counts["部分正确"] || 0) + (counts["错误"] || 0);
  const sections = {};
  for (const result of evalResults) {
    const section = result.section || "未分类";
    sections[section] ||= {};
    sections[section][result.verdict] = (sections[section][result.verdict] || 0) + 1;
  }
  const columns = ["正确", "部分正确", "错误", "无效回答", "需要澄清", "协议错误", "API失败"];
  const tableHeader = columns.map((column) => column).join(" | ");
  const tableSeparator = columns.map(() => "---").join(" | ");

  let report = `# 场外衍生品法规知识库问答评测报告

**评测时间**：${now()}
**模式**：${options.judgeOnly ? "缓存重判（不调用API）" : "API批量运行＋判定"}
**题数**：${total}
**输入答案**：${sourcePath || "本轮API运行"}

本报告将生命周期/结构状态与语义判定分开统计。只有形成 \`stage=complete\` 且通过答案结构与引用校验的回答，才进入“正确/部分正确/错误”语义统计。

## 总体结果

| 指标 | 数量 | 占比 |
|---|---:|---:|
| 正确 | ${counts["正确"] || 0} | ${pct(counts["正确"] || 0)}% |
| 部分正确 | ${counts["部分正确"] || 0} | ${pct(counts["部分正确"] || 0)}% |
| 错误 | ${counts["错误"] || 0} | ${pct(counts["错误"] || 0)}% |
| 无效回答 | ${counts["无效回答"] || 0} | ${pct(counts["无效回答"] || 0)}% |
| 需要澄清 | ${counts["需要澄清"] || 0} | ${pct(counts["需要澄清"] || 0)}% |
| 协议错误 | ${counts["协议错误"] || 0} | ${pct(counts["协议错误"] || 0)}% |
| API失败 | ${counts["API失败"] || 0} | ${pct(counts["API失败"] || 0)}% |
| 完整回答率 | ${completed} | ${pct(completed)}% |
| 语义有效回答率（正确+部分正确） | ${(counts["正确"] || 0) + (counts["部分正确"] || 0)} | ${pct((counts["正确"] || 0) + (counts["部分正确"] || 0))}% |

语义判定样本数为${semanticTotal}，生命周期或结构无效的${total - semanticTotal}题单独列出，不混入关键词正确率。

## 按章节统计

| 章节 | 题数 | ${tableHeader} |
|---|---:|${tableSeparator}|
`;

  for (const [section, sectionCounts] of Object.entries(sections)) {
    const sectionTotal = Object.values(sectionCounts).reduce((sum, count) => sum + count, 0);
    report += `| ${section} | ${sectionTotal} | ${columns.map((column) => sectionCounts[column] || 0).join(" | ")} |\n`;
  }

  const nonCorrect = evalResults.filter((result) => result.verdict !== "正确");
  report += `\n## 非完整正确题目\n\n`;
  if (nonCorrect.length === 0) report += "无。\n";
  else {
    for (const result of nonCorrect) {
      report += `- **${result.id}** [${result.verdict}] ${result.detail || ""}\n`;
    }
  }

  report += `\n## 评测口径\n\n`;
  report += "- 判断题按直接回答分句归一化监管模态词；后文限制性说明不改变主句极性。\n";
  report += "- 数值按数值、单位和边界运算符比较；交易日、自然日、月、年等单位不混同。\n";
  report += "- 引用校验只验证证据真实性和结构完整性，不把检索排名当作证据充分性的替代。\n";
  report += "- 评测器版本和输入哈希见同目录的 `00_run_manifest.json`。\n";
  return report;
}

function writeRunInputs(outputDir, questions) {
  writeJsonAtomic(join(outputDir, "01_questions_parsed.json"), questions);
  writeJsonAtomic(join(outputDir, "01_questions_only.json"), questions.map((q) => ({
    id: q.id,
    section: q.section,
    question: q.question,
    regulation: q.regulation,
  })));
}

function writeManifest(outputDir, manifest) {
  writeJsonAtomic(join(outputDir, "00_run_manifest.json"), manifest);
}

async function runApiEvaluation(options, questions) {
  ensureDir(options.outputDir);
  writeRunInputs(options.outputDir, questions);
  const progressPath = join(options.outputDir, "02_progress.json");
  const resultsPath = join(options.outputDir, "02_system_answers.jsonl");
  let completed = new Set();
  if (existsSync(progressPath) && !options.fresh) {
    const progress = JSON.parse(readFileSync(progressPath, "utf8"));
    completed = new Set(progress.completed || []);
    console.log(`从断点恢复：已完成${completed.size}题`);
  }

  const startTime = Date.now();
  let successCount = 0;
  let failCount = 0;
  for (let index = 0; index < questions.length; index += 1) {
    const question = questions[index];
    if (completed.has(question.id)) {
      console.log(`[${index + 1}/${questions.length}] ${question.id} 已缓存，跳过`);
      continue;
    }
    const started = Date.now();
    console.log(`\n[${index + 1}/${questions.length}] ${question.id} ${question.question.slice(0, 90)}`);
    const result = await queryWithRetry(question.question);
    const elapsedSeconds = Number(((Date.now() - started) / 1000).toFixed(1));
    const record = answerRecordFromResult(question, result, elapsedSeconds);
    writeFileSync(resultsPath, `${JSON.stringify(record)}\n`, { flag: "a" });
    completed.add(question.id);
    writeJsonAtomic(progressPath, { completed: [...completed], totalQuestions: questions.length, lastUpdated: now() });
    if (record.runStatus === "complete") {
      successCount += 1;
      console.log(`  ✓ 完成（${elapsedSeconds}s）→ ${record.systemConclusion.slice(0, 100)}`);
    } else {
      failCount += 1;
      console.log(`  ! ${record.runStatus}：${record.lifecycleError || record.lifecycleMessage || record.systemConclusion || "无回答"}`);
    }
  }
  console.log(`\nAPI运行结束：完成${successCount}题，生命周期/API异常${failCount}题，耗时${((Date.now() - startTime) / 60000).toFixed(1)}分钟`);
  return resultsPath;
}

function evaluateCachedAnswers(options, questions, inputPath) {
  const records = validateAnswerRecords(readJsonl(inputPath), questions, { ids: options.ids });
  const evalResults = records.map((record, index) => {
    const question = questions[index];
    return buildJudgment(record, question);
  });
  return { records, evalResults };
}

function generateOutputs(options, questions, records, evalResults, sourcePath) {
  const outputDir = options.outputDir;
  ensureDir(outputDir);
  writeRunInputs(outputDir, questions);
  if (!options.judgeOnly) {
    // API模式的答案文件已经在运行中增量写入；这里不重复写入。
  } else {
    writeTextAtomic(join(outputDir, "02_system_answers.jsonl"), `${records.map((record) => JSON.stringify(record)).join("\n")}\n`);
  }
  writeJsonAtomic(join(outputDir, "03_evaluation_results.json"), evalResults);
  writeTextAtomic(join(outputDir, "04_summary_report.md"), buildReport(evalResults, options, sourcePath));
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.fresh) assertFreshDir(options.outputDir);
  if (options.judgeOnly && existsSync(options.outputDir) && !options.fresh && !options.overwrite) {
    throw new Error("缓存重判为避免覆盖旧结果，必须使用 --fresh，或明确传入 --overwrite");
  }
  if (options.fresh && options.overwrite) throw new Error("--fresh 与 --overwrite 不能同时使用");

  const allQuestions = parseQuestions(options.questionFile);
  const questions = selectQuestions(allQuestions, options.ids);
  validateQuestionSet(questions, { ids: options.ids });
  console.log(`解析题库：${questions.length}题${options.ids ? "（抽样）" : ""}`);

  let records;
  let evalResults;
  let sourcePath = null;
  if (options.judgeOnly) {
    sourcePath = options.input;
    ({ records, evalResults } = evaluateCachedAnswers(options, questions, options.input));
  } else {
    sourcePath = await runApiEvaluation(options, questions);
    const allRecords = readJsonl(sourcePath);
    records = validateAnswerRecords(allRecords, questions, { ids: options.ids });
    evalResults = records.map((record, index) => buildJudgment(record, questions[index]));
  }

  generateOutputs(options, questions, records, evalResults, sourcePath);
  const manifest = {
    generatedAt: now(),
    mode: options.judgeOnly ? "judge-only" : "api-run",
    evaluatorVersion: "2026-07-20-lifecycle-v1",
    gitCommit: currentGitCommit(),
    projectRoot: PROJECT_ROOT,
    questionFile: options.questionFile,
    questionFileSha256: sha256File(options.questionFile),
    inputAnswersFile: sourcePath,
    inputAnswersSha256: sourcePath && existsSync(sourcePath) ? sha256File(sourcePath) : null,
    questionCount: questions.length,
    ids: options.ids ? [...options.ids] : null,
    outputDir: options.outputDir,
    counts: countVerdicts(evalResults),
  };
  writeManifest(options.outputDir, manifest);

  const counts = countVerdicts(evalResults);
  console.log(`\n评测完成：正确${counts["正确"] || 0}，部分正确${counts["部分正确"] || 0}，错误${counts["错误"] || 0}，结构/生命周期异常${(counts["无效回答"] || 0) + (counts["需要澄清"] || 0) + (counts["协议错误"] || 0) + (counts["API失败"] || 0)}`);
  console.log(`输出目录：${options.outputDir}`);
}

export {
  parseArgs,
  parseQuestions,
  validateAnswerStructure,
  classifyQuestion,
  findPolarityToken,
  extractQuantities,
  compareQuantities,
  normalizeComparableText,
  extractKeyPhrases,
  phraseMatches,
  judgeAnswer,
  askQuestion,
};

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    console.error(`评测脚本异常退出：${error.message}`);
    process.exit(1);
  });
}
