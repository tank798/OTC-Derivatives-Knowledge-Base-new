const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const test = require("node:test");
require("reflect-metadata");

const { QueryAnalysisService } = require("../apps/api/dist/apps/api/src/modules/query-analysis/query-analysis.service.js");
const { CitationValidatorService } = require("../apps/api/dist/apps/api/src/modules/citation-validator/citation-validator.service.js");
const { ContextBuilderService } = require("../apps/api/dist/apps/api/src/modules/context-builder/context-builder.service.js");
const { ComplianceService } = require("../apps/api/dist/apps/api/src/modules/compliance/compliance.service.js");

const analyzer = new QueryAnalysisService();
const validator = new CitationValidatorService();

function hit(overrides = {}) {
  return {
    source: "chunk", id: "chunk_1", documentId: "doc_1", chunkId: "chunk_1",
    title: "证券公司场外期权业务管理办法", publisher: "中国证券业协会",
    url: "https://example.org/rule", publishedAt: "2025-01-01", effectiveAt: "2025-01-01",
    articleNo: "第十条", articleEnd: "", chapterTitle: "第二章", documentNumber: "中证协发〔2025〕1号",
    text: "证券公司开展场外期权业务，应当符合交易商管理要求。", excerpt: "证券公司开展场外期权业务，应当符合交易商管理要求。",
    score: 1, authorityLevel: "", status: "现行有效", verificationStatus: "metadata",
    matchReason: "bm25 + vector + rrf", retrievalMethods: ["bm25", "vector", "rrf"], localFilePath: "data/raw/监管文件/test.pdf",
    ...overrides,
  };
}

function answer(overrides = {}) {
  return {
    directAnswer: "是",
    conclusion: "【明确规定】证券公司开展该业务应当满足交易商要求。",
    conclusionLabel: "有条件可做",
    productStructure: { underlyingAsset: "", productType: "场外期权", transactionStructure: "", counterparty: "证券公司", investorType: "", isCrossBorder: false, riskPoints: [], missingInfo: [] },
    regulatoryBasis: [{ evidenceId: "chunk_1", title: "伪造标题", publisher: "", url: "https://fake", articleNo: "第一百条", excerpt: "", requirement: "应满足交易商要求", status: "" }],
    restrictions: [], missingInfo: [], manualReviewNote: "", confidenceScore: "medium", confidenceReason: "",
    retrievalTrace: { chunkHits: 1, documentHits: 1, strategy: "hybrid" },
    ...overrides,
  };
}

test("问题规范化会识别雪球并进行受控扩展", () => {
  const result = analyzer.analyze("券商给合格投资人卖雪球，需要适当性和备案吗？");
  assert.match(result.normalizedQuery, /证券公司/);
  assert.ok(result.keywords.includes("场外期权"));
  assert.ok(result.keywords.includes("自动赎回"));
  assert.ok(result.topics.includes("投资者适当性"));
  assert.ok(result.topics.includes("备案与报告"));
});

test("Web代理固定连接新API的IPv4地址，避免命中旧IPv6后端", () => {
  const route = readFileSync("apps/web/app/api/proxy/[...path]/route.ts", "utf8");
  assert.match(route, /http:\/\/127\.0\.0\.1:4000\/api/);
  assert.doesNotMatch(route, /http:\/\/localhost:4000\/api/);
});

test("三个首版评测问题能识别主体、产品和投资比例主题", () => {
  const listedCompany = analyzer.analyze("上市公司可以做挂钩自己本身标的的场外衍生品吗");
  assert.ok(listedCompany.subjects.includes("上市公司"));
  assert.ok(listedCompany.topics.includes("准入"));
  assert.ok(listedCompany.keywords.includes("本公司股票"));

  const voucher = analyzer.analyze("券商收益凭证可以做雪球吗");
  assert.ok(voucher.subjects.includes("证券公司"));
  assert.ok(voucher.productTypes.includes("收益凭证"));
  assert.ok(voucher.productTypes.includes("雪球"));

  const privateProduct = analyzer.analyze("私募产品投资雪球比例的范围有明确规定吗");
  assert.ok(privateProduct.subjects.includes("私募产品"));
  assert.ok(privateProduct.topics.includes("投资比例"));
  assert.ok(privateProduct.keywords.includes("私募证券投资基金"));
});

test("引用校验使用检索元数据覆盖模型自造标题、条款和URL", () => {
  const checked = validator.validate(answer(), [hit()], analyzer.analyze("证券公司能否开展场外期权？"));
  assert.equal(checked.citationValidation.passed, true);
  assert.equal(checked.regulatoryBasis[0].title, hit().title);
  assert.equal(checked.regulatoryBasis[0].articleNo, hit().articleNo);
  assert.equal(checked.regulatoryBasis[0].url, hit().url);
});

test("上下文不存在的法规引用会被拒绝并降级为证据不足", () => {
  const draft = answer({ regulatoryBasis: [{ ...answer().regulatoryBasis[0], evidenceId: "chunk_missing" }] });
  const checked = validator.validate(draft, [hit()], analyzer.analyze("证券公司可以开展场外期权吗？"));
  assert.equal(checked.conclusionLabel, "需人工合规复核");
  assert.equal(checked.directAnswer, "不能确认");
  assert.match(checked.conclusion, /暂时无法形成确定结论/);
  assert.equal(checked.regulatoryBasis.length, 0);
});

test("效力状态未知时不得断言法规现行有效", () => {
  const checked = validator.validate(answer({ conclusion: "该办法仍然有效。" }), [hit({ status: "unknown" })], analyzer.analyze("该办法目前是否有效？"));
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.conclusion, /证据不足/);
});

test("没有URL时引用校验不会生成虚假URL", () => {
  const checked = validator.validate(answer(), [hit({ url: "" })], analyzer.analyze("场外期权交易商要求是什么？"));
  assert.equal(checked.regulatoryBasis[0].url, "");
});

test("上市公司自身股票挂钩问题缺少直接条文时拒绝强结论", () => {
  const query = analyzer.analyze("上市公司可以做挂钩自己本身标的的场外衍生品吗");
  const generalRule = hit({
    title: "上海证券交易所上市公司自律监管指引第5号——交易与关联交易",
    text: "上市公司拟开展场外衍生品交易的，应当评估交易必要性和交易对手信用风险。",
  });
  const checked = validator.validate(answer({ conclusion: "上市公司可以以本公司股票为标的开展场外衍生品交易。" }), [generalRule], query);
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.conclusion, /证据不足/);
});

test("上市公司自身股票问题必须区分交易对手禁止和未来生效规则", () => {
  const query = analyzer.analyze("上市公司可以做挂钩自己本身标的的场外衍生品吗");
  const currentRule = hit({
    id: "chunk_current",
    chunkId: "chunk_current",
    title: "期货风险管理公司衍生品交易业务管理规则",
    text: "期货风险管理公司不得与上市公司开展以本公司股票为标的的衍生品交易。",
  });
  const futureRule = hit({
    id: "chunk_future",
    chunkId: "chunk_future",
    title: "衍生品交易监督管理办法（试行）",
    status: "已公布、尚未施行",
    text: "上市公司不得达成以其发行的股票为合约标的物的衍生品交易。",
  });
  const draft = answer({
    conclusion: "上市公司可以开展该类场外衍生品交易。",
    regulatoryBasis: [{ evidenceId: "chunk_current", title: "", publisher: "", url: "", articleNo: "", excerpt: "", requirement: "存在特定交易路径禁止", status: "" }],
  });
  const checked = validator.validate(draft, [currentRule, futureRule], query);
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.confidenceReason, /交易路径|生效时点/);
});

test("收益凭证通用规则未直接列明雪球时拒绝无条件可做结论", () => {
  const query = analyzer.analyze("券商收益凭证可以做雪球吗");
  const generalRule = hit({
    title: "证券公司收益凭证发行管理办法",
    text: "证券公司发行浮动收益凭证，应当具有相应衍生品交易业务资格。",
  });
  const checked = validator.validate(answer({ conclusion: "证券公司可以无条件发行雪球收益凭证。" }), [generalRule], query);
  assert.equal(checked.citationValidation.passed, false);
  assert.match(checked.conclusion, /证据不足/);
});

test("收益凭证缺少雪球直接条文时允许不能确认的保守结论", () => {
  const query = analyzer.analyze("券商收益凭证可以做雪球吗");
  const generalRule = hit({
    title: "证券公司收益凭证发行管理办法",
    text: "证券公司发行浮动收益凭证，应当具有相应衍生品交易业务资格。",
  });
  const checked = validator.validate(answer({
    directAnswer: "不能确认",
    conclusion: "现有通用规则未直接列明雪球结构，不能确认明确允许。",
    conclusionLabel: "需人工合规复核",
  }), [generalRule], query);
  assert.equal(checked.citationValidation.passed, true);
  assert.equal(checked.directAnswer, "不能确认");
});

test("同一证据被模型重复引用时合并要求而不重复展示", () => {
  const duplicated = answer({
    regulatoryBasis: [
      { evidenceId: "chunk_1", title: "", publisher: "", url: "", articleNo: "", excerpt: "", requirement: "要求一", status: "" },
      { evidenceId: "chunk_1", title: "", publisher: "", url: "", articleNo: "", excerpt: "", requirement: "要求二", status: "" },
    ],
  });
  const checked = validator.validate(duplicated, [hit()], analyzer.analyze("证券公司能否开展场外期权？"));
  assert.equal(checked.regulatoryBasis.length, 1);
  assert.match(checked.regulatoryBasis[0].requirement, /要求一；要求二/);
});

test("私募证券基金雪球25%直接条文可通过引用校验", () => {
  const query = analyzer.analyze("私募产品投资雪球比例的范围有明确规定吗");
  const directRule = hit({
    title: "私募证券投资基金运作指引",
    articleNo: "第十七条",
    text: "参与带敲入和敲出结构的场外期权或者收益凭证（如雪球结构衍生品）的合约名义本金不得超过基金净资产的25%。",
  });
  const checked = validator.validate(answer({
    conclusion: "【明确规定】原则上合约名义本金不得超过基金净资产的25%。",
    regulatoryBasis: [{ evidenceId: "chunk_1", title: "", publisher: "", url: "", articleNo: "", excerpt: "", requirement: "原则上不超过25%", status: "" }],
  }), [directRule], query);
  assert.equal(checked.citationValidation.passed, true);
});

test("端到端服务共用规范化、检索、上下文、回答和引用校验链路", async () => {
  const fakeLlm = { isConfigured: true, chat: async () => JSON.stringify({ directAnswer: "是", conclusion: "是，符合交易商要求时可以开展。", conclusionLabel: "有条件可做", regulatoryBasis: [{ evidenceId: "chunk_1", requirement: "应符合交易商要求" }], restrictions: ["仅适用于规则覆盖主体"], missingInfo: [], manualReviewNote: "" }) };
  const fakeRetrieval = { search: async () => [hit()] };
  const service = new ComplianceService(fakeLlm, fakeRetrieval, analyzer, new ContextBuilderService(), validator, { getComplianceAgentPrompt: () => "严格执行证据约束" });
  const result = await service.answer("券商可以开展场外期权吗？");
  assert.equal(result.queryAnalysis.productTypes.includes("场外期权"), true);
  assert.equal(result.answer.citationValidation.passed, true);
  assert.equal(result.answer.directAnswer, "是");
  assert.doesNotMatch(result.answer.conclusion, /^是[，,。]/);
  assert.equal(result.answer.regulatoryBasis[0].evidenceId, "chunk_1");
});

test("初答引用校验失败时使用同一批证据修订一次", async () => {
  let calls = 0;
  const fakeLlm = {
    isConfigured: true,
    chat: async (_system, prompt) => {
      calls += 1;
      if (calls === 1) return JSON.stringify({ directAnswer: "是", conclusion: "可以发行雪球收益凭证。", conclusionLabel: "可做", regulatoryBasis: [{ evidenceId: "chunk_1", requirement: "可发行" }], restrictions: [], missingInfo: [], manualReviewNote: "" });
      assert.match(prompt, /上一次回答未通过系统引用校验/);
      assert.match(prompt, /缺少直接授权条文/);
      return JSON.stringify({ directAnswer: "不能确认", conclusion: "通用规则未直接列明雪球结构，不能确认明确允许。", conclusionLabel: "需人工合规复核", regulatoryBasis: [{ evidenceId: "chunk_1", requirement: "浮动收益凭证须具备衍生品资格" }], restrictions: [], missingInfo: ["缺少直接授权条文"], manualReviewNote: "" });
    },
  };
  const voucherHit = hit({ title: "证券公司收益凭证发行管理办法", text: "证券公司发行浮动收益凭证，应当具有相应衍生品交易业务资格。" });
  const service = new ComplianceService(fakeLlm, { search: async () => [voucherHit] }, analyzer, new ContextBuilderService(), validator, { getComplianceAgentPrompt: () => "证据约束" });
  const result = await service.answer("券商收益凭证可以做雪球吗");
  assert.equal(calls, 2);
  assert.equal(result.answer.directAnswer, "不能确认");
  assert.equal(result.answer.citationValidation.passed, true);
});
