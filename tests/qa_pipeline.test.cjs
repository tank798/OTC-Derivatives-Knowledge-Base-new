const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { execFileSync } = require("node:child_process");
const test = require("node:test");
require("reflect-metadata");

const { QueryAnalysisService } = require("../apps/api/dist/apps/api/src/modules/query-analysis/query-analysis.service.js");
const { CitationValidatorService } = require("../apps/api/dist/apps/api/src/modules/citation-validator/citation-validator.service.js");
const { ContextBuilderService } = require("../apps/api/dist/apps/api/src/modules/context-builder/context-builder.service.js");
const { AgentWorkflowService } = require("../apps/api/dist/apps/api/src/modules/compliance/agent-workflow.service.js");
const { HybridRegulationSearchTool } = require("../apps/api/dist/apps/api/src/modules/compliance/hybrid-regulation-search.tool.js");
const { ComplianceService } = require("../apps/api/dist/apps/api/src/modules/compliance/compliance.service.js");

const analyzer = new QueryAnalysisService();
const validator = new CitationValidatorService();
const RULE_TEXT = "证券公司开展场外期权业务，应当符合交易商管理要求。";

function hit(overrides = {}) {
  return {
    source: "chunk", id: "chunk_1", documentId: "doc_1", chunkId: "chunk_1",
    title: "证券公司场外期权业务管理办法", publisher: "中国证券业协会",
    url: "https://example.org/rule", publishedAt: "2025-01-01", effectiveAt: "2025-01-01",
    articleNo: "第十条", articleEnd: "", chapterTitle: "第二章", documentNumber: "中证协发〔2025〕1号",
    text: RULE_TEXT, excerpt: RULE_TEXT, score: 1, authorityLevel: "", status: "现行有效",
    verificationStatus: "metadata", matchReason: "bm25 + vector + rrf",
    retrievalMethods: ["bm25", "vector", "rrf"], localFilePath: "data/raw/监管文件/test.pdf",
    bm25Rank: 1, vectorRank: 2, rrfRank: 1, isSupplementalContext: false, subQuestion: "业务准入",
    ...overrides,
  };
}

function draft(overrides = {}) {
  return {
    directAnswer: "是", conclusionLevel: "明确规定", conclusion: "符合交易商要求时可以开展。",
    conclusionLabel: "有条件可做",
    scope: { subject: "证券公司", product: "场外期权", counterparty: "", time: "当前", conditions: ["符合交易商要求"] },
    productStructure: { underlyingAsset: "", productType: "场外期权", transactionStructure: "", counterparty: "", investorType: "证券公司", isCrossBorder: false, riskPoints: [], missingInfo: [] },
    regulatoryBasis: [{ evidenceId: "chunk_1", title: "伪造标题", publisher: "", url: "https://fake", articleNo: "第一百条", excerpt: RULE_TEXT, quoteExact: RULE_TEXT, requirement: "应符合交易商要求", status: "" }],
    restrictions: [], missingInfo: [], manualReviewNote: "", confidenceScore: "high", confidenceReason: "",
    ...overrides,
  };
}

function plan(overrides = {}) {
  return {
    normalizedQuery: "证券公司可以开展场外期权吗",
    legalIssue: "业务准入", subjects: ["证券公司"], productTypes: ["场外期权"],
    counterparties: [], timeScope: "当前", ambiguities: [],
    subQuestions: [{ id: "sq1", question: "证券公司开展场外期权的准入规则", queries: ["证券公司 场外期权 交易商资格"], formalTerms: ["场外期权交易商"], requiredEvidence: ["直接准入规定"] }],
    reasonSummary: "按主体和产品检索直接准入规定", ...overrides,
  };
}

function assessment(overrides = {}) {
  return {
    sufficient: true, answerability: "YES", evidenceLevel: "DIRECT",
    supportedSubQuestions: ["业务准入"], missingSubQuestions: [], missingEvidenceTypes: [],
    followUpQueries: [], reasonSummary: "存在主体和产品范围明确的直接规定", ...overrides,
  };
}

function modelAnswer(overrides = {}) {
  return {
    directAnswer: "是", conclusionLevel: "明确规定", conclusion: "是，符合交易商要求时可以开展。",
    scope: { subject: "证券公司", product: "场外期权", counterparty: "", time: "当前", conditions: ["符合交易商要求"] },
    regulatoryBasis: [{ evidenceId: "chunk_1", quoteExact: RULE_TEXT, supports: "应符合交易商要求" }],
    restrictions: [], missingInfo: [], manualReviewNote: "", confidence: "high", ...overrides,
  };
}

function makeHarness(options = {}) {
  const calls = [];
  const toolInputs = [];
  const planQueue = [...(options.plans ?? [plan()])];
  const assessQueue = [...(options.assessments ?? [assessment()])];
  const answerQueue = [...(options.answers ?? [modelAnswer()])];
  const reviewQueue = [...(options.reviews ?? [{ verdict: "PASS", issues: [], repairInstructions: [], missingEvidence: [], followUpQueries: [] }])];
  const llm = {
    isConfigured: options.configured !== false,
    modelName: "deepseek-v4-pro",
    chat: async (system, user) => {
      calls.push({ system, user });
      if (system === "PLANNER" && user.includes("mode: PLAN")) {
        const value = planQueue.shift(); return typeof value === "string" ? value : JSON.stringify(value);
      }
      if (system === "PLANNER") return JSON.stringify(assessQueue.shift() ?? assessment());
      if (system === "ANSWER") return JSON.stringify(answerQueue.shift() ?? modelAnswer());
      if (system === "REVIEWER") return JSON.stringify(reviewQueue.shift() ?? { verdict: "PASS", issues: [], repairInstructions: [], missingEvidence: [], followUpQueries: [] });
      throw new Error("unexpected prompt");
    },
  };
  const toolHitRounds = [...(options.hitRounds ?? [[hit()]])];
  const searchTool = {
    name: "hybrid_regulation_search",
    execute: async (input) => {
      toolInputs.push(input);
      return { ok: true, tool: "hybrid_regulation_search", input, hits: toolHitRounds.shift() ?? [hit()] };
    },
  };
  const prompts = { getPlannerPrompt: () => "PLANNER", getAnswerPrompt: () => "ANSWER", getReviewerPrompt: () => "REVIEWER" };
  const workflow = new AgentWorkflowService(llm, analyzer, new ContextBuilderService(), validator, prompts, searchTool);
  return { service: new ComplianceService(workflow), workflow, calls, toolInputs };
}

test("雪球基础降级分析包含敲入敲出、场外期权和收益凭证方向", () => {
  const result = analyzer.analyze("券商收益凭证可以做雪球吗");
  assert.ok(result.keywords.includes("场外期权"));
  assert.ok(result.keywords.includes("自动赎回"));
  assert.ok(result.keywords.includes("敲入"));
  assert.ok(result.keywords.includes("敲出"));
  assert.ok(result.productTypes.includes("收益凭证"));
  const promptText = readFileSync("packages/prompts/agent/retrieval-planner.md", "utf8");
  assert.match(promptText, /敲入敲出/); assert.match(promptText, /浮动收益凭证/);
});

test("不同主体的模型计划会产生不同检索工具输入", async () => {
  const securities = makeHarness({ plans: [plan()] });
  await securities.service.answer("证券公司可以开展场外期权吗", { debug: true });
  const futuresPlan = plan({ subjects: ["期货风险管理公司"], subQuestions: [{ ...plan().subQuestions[0], queries: ["期货风险管理公司 场外衍生品 交易对手"] }] });
  const futures = makeHarness({ plans: [futuresPlan] });
  await futures.service.answer("期货风险管理公司可以做场外衍生品吗", { debug: true });
  assert.deepEqual(securities.toolInputs[0].subjects, ["证券公司"]);
  assert.deepEqual(futures.toolInputs[0].subjects, ["期货风险管理公司"]);
});

test("混合检索工具拒绝越界参数且不会调用底层检索", async () => {
  let called = false;
  const tool = new HybridRegulationSearchTool({ hybridSearch: async () => { called = true; return []; } });
  const result = await tool.execute({ queries: [], subQuestion: "", topK: 200 });
  assert.equal(result.ok, false);
  assert.equal(called, false);
  assert.match(result.error, /参数无效/);
});

test("直接回答携带简短解释时安全归一为是否枚举", async () => {
  const harness = makeHarness({ answers: [modelAnswer({ directAnswer: "否，不能笼统认定可以", conclusion: "不能笼统认定可以开展。" })] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.answer.directAnswer, "否");
});

test("规划模型输出非法 JSON 时安全降级为规则计划", async () => {
  const harness = makeHarness({ plans: ["not-json"] });
  const result = await harness.service.answer("券商收益凭证可以做雪球吗", { debug: true });
  assert.equal(result.retrievalPlan.fallbackUsed, true);
  assert.ok(result.retrievalPlan.subQuestions[0].queries.some((query) => query.includes("场外期权")));
});

test("第一轮证据不足会触发第二轮检索", async () => {
  const harness = makeHarness({ assessments: [assessment({ sufficient: false, answerability: "UNCERTAIN", evidenceLevel: "INSUFFICIENT", missingSubQuestions: ["缺少例外"], missingEvidenceTypes: ["例外"], followUpQueries: ["场外期权 例外 豁免"] }), assessment()] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.agentTrace.retrievalRounds, 2);
  assert.equal(harness.toolInputs.length, 2);
  assert.deepEqual(harness.toolInputs[1].queries, ["场外期权 例外 豁免"]);
});

test("证据持续不足时最多检索两轮", async () => {
  const insufficient = assessment({ sufficient: false, answerability: "UNCERTAIN", evidenceLevel: "INSUFFICIENT", missingSubQuestions: ["缺直接规则"], missingEvidenceTypes: ["直接规定"], followUpQueries: ["直接规定"] });
  const harness = makeHarness({ assessments: [insufficient, insufficient] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.agentTrace.retrievalRounds, 2);
  assert.equal(harness.toolInputs.length, 2);
});

test("伪造 evidence_id 会被确定性校验拒绝", () => {
  const checked = validator.validate(draft({ regulatoryBasis: [{ ...draft().regulatoryBasis[0], evidenceId: "chunk_fake" }] }), [hit()], analyzer.analyze("证券公司可以开展场外期权吗"));
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.citationValidation.issues.join("\n"), /不存在/);
});

test("quoteExact 改动一个字即校验失败", () => {
  const changed = RULE_TEXT.replace("应当", "必须");
  const checked = validator.validate(draft({ regulatoryBasis: [{ ...draft().regulatoryBasis[0], excerpt: changed, quoteExact: changed }] }), [hit()], analyzer.analyze("证券公司可以开展场外期权吗"));
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.citationValidation.issues.join("\n"), /连续逐字原文/);
});

test("仅空白和全半角差异可回切为 Chunk 中的连续原始引文", async () => {
  const raw = "证券公司开展\n场外期权业务，应当符合交易商管理要求。";
  const collapsed = "证券公司开展场外期权业务,应当符合交易商管理要求。";
  const harness = makeHarness({ hitRounds: [[hit({ text: raw, excerpt: raw })]], answers: [modelAnswer({ regulatoryBasis: [{ evidenceId: "chunk_1", quoteExact: collapsed, supports: "应符合交商要求" }] })] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.answer.citationValidation.passed, true);
  assert.equal(result.answer.regulatoryBasis[0].quoteExact, raw);
});

test("quoteExact 修改比例、金额、日期或期限均会失败", async (t) => {
  const original = "合约名义本金不得超过净资产的25%，金额为1000万元，自2025年1月1日起三年内有效。";
  for (const [name, changed] of [["ratio", original.replace("25%", "30%")], ["amount", original.replace("1000万元", "2000万元")], ["date", original.replace("2025年1月1日", "2026年1月1日")], ["term", original.replace("三年", "两年")]]) {
    await t.test(name, () => {
      const evidence = hit({ text: original, excerpt: original });
      const checked = validator.validate(draft({ regulatoryBasis: [{ ...draft().regulatoryBasis[0], excerpt: changed, quoteExact: changed }] }), [evidence], analyzer.analyze("该限制是什么"));
      assert.equal(checked.citationValidation.passed, false);
    });
  }
});

test("法规 URL、标题和条款只由系统元数据回填", () => {
  const checked = validator.validate(draft(), [hit()], analyzer.analyze("证券公司可以开展场外期权吗"));
  assert.equal(checked.citationValidation.passed, true);
  assert.equal(checked.regulatoryBasis[0].url, "https://example.org/rule");
  assert.equal(checked.regulatoryBasis[0].title, hit().title);
  assert.equal(checked.regulatoryBasis[0].articleNo, "第十条");
});

test("尚未施行规则不能被写成当前规则", () => {
  const future = hit({ status: "已公布、尚未施行" });
  const checked = validator.validate(draft({ conclusion: "当前可以开展。", scope: { ...draft().scope, time: "当前" } }), [future], analyzer.analyze("当前可以开展吗"));
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.citationValidation.issues.join("\n"), /尚未施行/);
});

test("自身股票问题已引用现行交易对手禁止和未来一般禁止时，实质否定归一为否", () => {
  const currentText = "期货风险管理公司不得与上市公司开展以本公司股票为标的的衍生品交易。";
  const futureText = "上市公司不得达成以其发行的股票为合约标的物的衍生品交易。";
  const hits = [hit({ id: "chunk_current", chunkId: "chunk_current", text: currentText, excerpt: currentText }), hit({ id: "chunk_future", chunkId: "chunk_future", text: futureText, excerpt: futureText, status: "已公布、尚未施行" })];
  const checked = validator.validate(draft({
    directAnswer: "不能确认", conclusionLevel: "基于法规的推导", conclusion: "现行交易对手路径实际操作难以，未来规则尚未施行且将明确禁止。", conclusionLabel: "需人工合规复核",
    regulatoryBasis: [
      { ...draft().regulatoryBasis[0], evidenceId: "chunk_current", excerpt: currentText, quoteExact: currentText },
      { ...draft().regulatoryBasis[0], evidenceId: "chunk_future", excerpt: futureText, quoteExact: futureText },
    ],
  }), hits, analyzer.analyze("上市公司可以做挂钩自己本身股票的场外衍生品吗"));
  assert.equal(checked.citationValidation.passed, true);
  assert.equal(checked.directAnswer, "否");
});

test("私募证券基金的同一资产口径不得跨制度套用给集合资管计划", () => {
  const privateText = "参与带敲入和敲出结构的场外期权或者收益凭证(如雪球结构衍生品)的合约名义本金不得超过基金净资产的 25%。";
  const planText = "一个集合资产管理计划投资于同一资产的资金,不得超过该计划资产净值的 25%。";
  const mappingText = "场外期权及证券公司发行的非保本型收益凭证按照同一交易对手方视为同一资产。";
  const hits = [
    hit({ id: "chunk_private", chunkId: "chunk_private", title: "私募证券投资基金运作指引", text: privateText, excerpt: privateText }),
    hit({ id: "chunk_plan", chunkId: "chunk_plan", title: "证券期货经营机构私募资产管理计划运作管理规定", text: planText, excerpt: planText }),
    hit({ id: "chunk_mapping", chunkId: "chunk_mapping", title: "私募证券投资基金运作指引", text: mappingText, excerpt: mappingText }),
  ];
  const basis = hits.map((item) => ({ evidenceId: item.id, title: "", publisher: "", url: "", articleNo: "", excerpt: item.text, quoteExact: item.text, requirement: "支持比例结论", status: "" }));
  const checked = validator.validate(draft({
    directAnswer: "是", conclusion: "私募证券基金和集合资产管理计划投资雪球均适用25%上限。",
    scope: { ...draft().scope, subject: "私募证券基金、集合资产管理计划", product: "雪球" }, regulatoryBasis: basis,
  }), hits, analyzer.analyze("私募产品投资雪球比例的范围有明确规定吗"));
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.citationValidation.issues.join("\n"), /跨制度套用/);
});

test("审查返回 REPAIR 时只修订一次并最多复审一次", async () => {
  const harness = makeHarness({
    answers: [modelAnswer(), modelAnswer({ conclusion: "是，在明确限定主体和条件后可以开展。" })],
    reviews: [{ verdict: "REPAIR", issues: [{ type: "SCOPE", severity: "MAJOR", statement: "范围不明", evidenceId: "chunk_1", reason: "需限定主体", action: "修订" }], repairInstructions: ["限定主体"], missingEvidence: [], followUpQueries: [] }, { verdict: "PASS", issues: [], repairInstructions: [], missingEvidence: [], followUpQueries: [] }],
  });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.agentTrace.repairCount, 1); assert.equal(result.agentTrace.reviewCount, 2);
  assert.equal(harness.calls.filter((call) => call.system === "ANSWER").length, 2);
  assert.equal(result.answer.reviewValidation.passed, true);
});

test("审查模型将修订意见输出为对象时可安全归一为字符串", async () => {
  const harness = makeHarness({ reviews: [{ verdict: "PASS", issues: [], repairInstructions: [{ instruction: "限定主体" }], missingEvidence: [], followUpQueries: [] }] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.answer.reviewValidation.passed, true);
  assert.deepEqual(result.reviewResult.repairInstructions, ["限定主体"]);
});

test("收益凭证雪球缺少直接许可时，修订 Prompt 强制改为不能确认", async () => {
  const voucherText = "证券公司发行浮动收益凭证,应当具有相应衍生品交易业务资格。";
  const basis = [{ evidenceId: "chunk_1", quoteExact: voucherText, supports: "发行浮动收益凭证需具备衍生品业务资格" }];
  const harness = makeHarness({
    hitRounds: [[hit({ title: "证券公司收益凭证发行管理办法", text: voucherText, excerpt: voucherText })]],
    answers: [modelAnswer({ regulatoryBasis: basis }), modelAnswer({ directAnswer: "不能确认", conclusionLevel: "证据不足", conclusion: "现有通用规则未直接列明或许可雪球结构，不能确认。", regulatoryBasis: basis, confidence: "low" })],
  });
  const result = await harness.service.answer("券商收益凭证可以做雪球吗", { debug: true });
  const answerCalls = harness.calls.filter((call) => call.system === "ANSWER");
  assert.equal(answerCalls.length, 2);
  assert.match(answerCalls[1].user, /mandatory_direct_answer: 不能确认/);
  assert.equal(result.answer.directAnswer, "不能确认");
  assert.match(result.answer.confidenceReason, /不足以支持确定性/);
  assert.equal(result.answer.reviewValidation.passed, true);
});

test("审查返回 RETRIEVE 时受两轮检索上限控制", async () => {
  const insufficient = assessment({ sufficient: false, answerability: "UNCERTAIN", evidenceLevel: "INSUFFICIENT", missingSubQuestions: ["例外"], missingEvidenceTypes: ["例外"], followUpQueries: ["例外规则"] });
  const harness = makeHarness({ assessments: [insufficient, assessment()], reviews: [{ verdict: "RETRIEVE", issues: [], repairInstructions: [], missingEvidence: ["直接例外"], followUpQueries: ["直接例外"] }] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.agentTrace.retrievalRounds, 2);
  assert.equal(result.answer.directAnswer, "不能确认");
  assert.match(result.agentTrace.degradationReason, /两轮检索已用完/);
});

test("达到修订或审查上限后稳定降级为不能确认", async () => {
  const repair = { verdict: "REPAIR", issues: [{ type: "SCOPE", severity: "MAJOR", statement: "仍超范围", evidenceId: "chunk_1", reason: "仍超范围", action: "修订" }], repairInstructions: ["修订"], missingEvidence: [], followUpQueries: [] };
  const harness = makeHarness({ answers: [modelAnswer(), modelAnswer()], reviews: [repair, repair] });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.answer.directAnswer, "不能确认"); assert.equal(result.agentTrace.repairCount, 1);
  assert.equal(result.agentTrace.degraded, true);
});

test("无 API key 时返回明确降级状态，不伪装完成智能回答", async () => {
  const harness = makeHarness({ configured: false });
  const result = await harness.service.answer("证券公司可以开展场外期权吗", { debug: true });
  assert.equal(result.answer.directAnswer, "不能确认"); assert.equal(result.agentTrace.degraded, true);
  assert.match(result.agentTrace.degradationReason, /LLM_API_KEY/);
  assert.equal(result.agentTrace.llmCalls, 0);
});

test("普通接口结果不返回内部状态轨迹和审查意见", async () => {
  const harness = makeHarness();
  const result = await harness.service.answer("证券公司可以开展场外期权吗");
  assert.equal(result.agentTrace, undefined);
  assert.equal(result.retrievalPlan, undefined);
  assert.equal(result.evidenceAssessment, undefined);
  assert.equal(result.reviewResult, undefined);
});

test("生产 API、流式 API 和评测脚本共用 ComplianceService", () => {
  const controller = readFileSync("apps/api/src/modules/compliance/compliance.controller.ts", "utf8");
  const evaluator = readFileSync("scripts/evaluate_retrieval.mjs", "utf8");
  assert.match(controller, /this\.compliance\.answer/); assert.match(controller, /answerStream/);
  assert.match(evaluator, /new ComplianceService|ComplianceService/);
});

test("API key 不出现在受控智能体代码、Prompt 或 Git 差异中", () => {
  const paths = [
    "apps/api/src/modules/compliance/agent-workflow.service.ts",
    "packages/prompts/agent/retrieval-planner.md",
    "packages/prompts/agent/evidence-answer.md",
    "packages/prompts/agent/answer-reviewer.md",
  ];
  const text = paths.map((path) => readFileSync(path, "utf8")).join("\n");
  assert.doesNotMatch(text, /sk-[A-Za-z0-9]{12,}/);
  const diff = execFileSync("git", ["diff"], { encoding: "utf8" });
  assert.doesNotMatch(diff, /sk-[A-Za-z0-9]{12,}/);
});
