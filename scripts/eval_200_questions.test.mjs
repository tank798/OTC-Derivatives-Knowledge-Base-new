import test from "node:test";
import assert from "node:assert/strict";

import {
  askQuestion,
  compareQuantities,
  judgeAnswer,
  parseQuestions,
  validateAnswerStructure,
} from "./eval_200_questions.mjs";

const validAnswer = (conclusion, overrides = {}) => ({
  conclusion,
  reasoningSummary: "依据直接法规条款说明适用范围和边界。",
  regulatoryBasis: [{ evidenceId: "chunk_test", quoteExact: "连续逐字原文", explanation: "说明该原文对结论的作用。" }],
  wikiBasis: [],
  citationValidation: { passed: true, issues: [] },
  ...overrides,
});

test("题库完整解析为200题且题号唯一", () => {
  const questions = parseQuestions("场外衍生品法规问答题库_200题_20260719.md");
  assert.equal(questions.length, 200);
  assert.equal(new Set(questions.map((question) => question.id)).size, 200);
});

test("法规否定同义词按直接回答极性归一", () => {
  const result = judgeAnswer(
    validAnswer("不得与一级交易商之外的交易对手开展该业务。"),
    "不能与一级交易商之外的交易对手开展该业务。",
    "证券公司能否开展该业务？",
  );
  assert.equal(result.verdict, "正确");
  assert.equal(result.polarityMatch, true);
});

test("后文限制不翻转前面的肯定主句", () => {
  const result = judgeAnswer(
    validAnswer("可以设置该类限额，但不得违反适用的风险管理要求。"),
    "可以设置该类限额。",
    "证券公司是否可以设置该类限额？",
  );
  assert.equal(result.verdict, "正确");
  assert.equal(result.polarityMatch, true);
});

test("数值比较保留单位和边界运算符", () => {
  assert.equal(compareQuantities("不低于百分之二十", "不低于20%").matched, true);
  assert.equal(compareQuantities("不超过20个交易日", "不超过20日").matched, false);
  assert.equal(compareQuantities("不超过5个工作日", "不超过5个交易日").matched, false);
  assert.equal(compareQuantities("超过百分之二十", "不超过20%").matched, false);
});

test("确定性结论缺少依据时结构无效", () => {
  const result = validateAnswerStructure(validAnswer("不得开展该业务。", {
    regulatoryBasis: [],
  }));
  assert.equal(result.valid, false);
  assert.match(result.reasons.join("；"), /没有法规依据/u);
});

test("证据不足结论允许没有直接依据但仍须通过引用校验", () => {
  const result = validateAnswerStructure(validAnswer("根据当前知识库，无法得出确定结论。", {
    regulatoryBasis: [],
  }));
  assert.equal(result.valid, true);
  assert.equal(result.insufficient, true);
});

test("缺少citationValidation的旧式答案不进入语义评分", () => {
  const result = judgeAnswer({ conclusion: "超过20%。", reasoningSummary: "说明。" }, "超过20%。", "偏离多少？");
  assert.equal(result.verdict, "无效回答");
  assert.equal(result.structureStatus, "invalid");
});

test("澄清阶段不被评测器机械回复是", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (_url, init) => {
    calls.push(JSON.parse(init.body));
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ success: true, data: {
        sessionId: "session-clarify",
        stage: "awaiting_clarification",
        message: "请补充主体",
      } }),
    };
  };
  try {
    const result = await askQuestion("问题");
    assert.equal(result.runStatus, "needs_clarification");
    assert.equal(calls.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("只有问题确认阶段才自动发送是，并使用最新阶段", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  const responses = [
    { sessionId: "session-complete", stage: "awaiting_confirmation", proposedQuery: "规范化问题" },
    { sessionId: "session-complete", stage: "complete", answer: validAnswer("可以。") },
  ];
  globalThis.fetch = async (_url, init) => {
    calls.push(JSON.parse(init.body));
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ success: true, data: responses.shift() }),
    };
  };
  try {
    const result = await askQuestion("问题");
    assert.equal(result.runStatus, "complete");
    assert.equal(calls.length, 2);
    assert.equal(calls[1].message, "是");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
