import assert from "node:assert/strict";
import test from "node:test";

import { CitationValidatorService } from "../../apps/api/dist/apps/api/src/modules/citation-validator/citation-validator.service.js";
import { ComplianceController } from "../../apps/api/dist/apps/api/src/modules/compliance/compliance.controller.js";
import {
  RegulatoryAgentService,
} from "../../apps/api/dist/apps/api/src/modules/compliance/regulatory-agent.service.js";
import { LlmRequestAbortedError } from "../../apps/api/dist/apps/api/src/modules/llm/llm.service.js";

function createAgent(chatWithTools) {
  return new RegulatoryAgentService(
    {
      isConfigured: true,
      modelName: "test-model",
      fastModelName: "test-fast-model",
      chatWithTools,
    },
    {
      getAgentPrompt: () => "test prompt",
      getAgentPromptPath: () => "test.md",
    },
    { execute: async () => ({ ok: true, hits: [] }) },
    { build: () => "" },
    new CitationValidatorService(),
    { write: () => undefined },
  );
}

function responseMock() {
  return {
    statusCode: 200,
    status(code) {
      this.statusCode = code;
      return this;
    },
  };
}

test("确定性结论不能在零引用下通过证据门禁", () => {
  const result = new CitationValidatorService().validateDraft({
    conclusion: "可以开展该业务。",
    reasoningSummary: "测试",
    regulatoryBasis: [],
    missingInformation: [],
    manualReviewNote: "",
  }, []);
  assert.equal(result.answer.citationValidation.passed, false);
  assert.match(result.issues.join("；"), /确定性法规结论/);
});

test("证据不足回答可以无引用返回", () => {
  const result = new CitationValidatorService().validateDraft({
    conclusion: "现有证据不足，无法得出确定结论。",
    reasoningSummary: "测试",
    regulatoryBasis: [],
    missingInformation: [],
    manualReviewNote: "",
  }, []);
  assert.equal(result.answer.citationValidation.passed, true);
});

test("模型首次未调用工具时会反馈协议错误并自动纠偏", async () => {
  let calls = 0;
  const agent = createAgent(async (_system, messages) => {
    calls += 1;
    if (calls === 1) {
      return { content: "这是绕过工具的普通回答", toolCalls: [], finishReason: "stop" };
    }
    assert.match(messages.at(-1)?.content ?? "", /只调用以下允许工具/);
    return {
      content: null,
      toolCalls: [{ id: "rewrite-1", name: "present_rewritten_question", arguments: { rewrittenQuery: "测试问题？" } }],
      finishReason: "tool_calls",
    };
  });
  const response = await agent.run("测试问题");
  assert.equal(response.stage, "awaiting_confirmation");
  assert.equal(calls, 2);
});

test("模型连续绕过工具时有界重试且不展示普通文本", async () => {
  let calls = 0;
  const agent = createAgent(async () => {
    calls += 1;
    return {
      content: "这是绕过工具的普通回答",
      toolCalls: [],
      finishReason: "stop",
    };
  });
  await assert.rejects(agent.run("测试问题"), (error) => error?.code === "AGENT_PROTOCOL_ERROR");
  assert.equal(calls, 3);
  const session = [...agent.sessions.values()][0];
  assert.equal(session.messages.length, 0);
});

test("同一 session 的并发请求会被拒绝", async () => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const agent = createAgent(async () => {
    await pending;
    return { content: "无工具", toolCalls: [], finishReason: "stop" };
  });

  const first = agent.run("第一条消息");
  await new Promise((resolve) => setImmediate(resolve));
  const sessionId = [...agent.sessions.keys()][0];
  await assert.rejects(agent.run("第二条消息", { sessionId }), (error) => error?.code === "SESSION_BUSY");
  release();
  await assert.rejects(first, (error) => error?.code === "AGENT_PROTOCOL_ERROR");
});

test("取消请求会回滚本轮会话消息", async () => {
  const agent = createAgent((_system, _messages, _tools, _timeout, options) => new Promise((_, reject) => {
    options.signal.addEventListener("abort", () => reject(new LlmRequestAbortedError()), { once: true });
  }));
  const controller = new AbortController();
  const run = agent.run("会被取消的问题", { signal: controller.signal });
  await new Promise((resolve) => setImmediate(resolve));
  const session = [...agent.sessions.values()][0];
  controller.abort();
  await assert.rejects(run, (error) => error?.code === "REQUEST_ABORTED");
  assert.equal(session.messages.length, 0);
  assert.equal(session.busy, false);
});

test("Controller 对畸形请求返回 400 而不是抛出 TypeError", async () => {
  let complianceCalled = false;
  const controller = new ComplianceController(
    { answer: async () => { complianceCalled = true; } },
    { isReady: true },
  );
  const response = responseMock();
  const result = await controller.query({ message: 123 }, response);
  assert.equal(response.statusCode, 400);
  assert.equal(result.success, false);
  assert.equal(result.error.code, "INVALID_REQUEST");
  assert.equal(complianceCalled, false);
});
