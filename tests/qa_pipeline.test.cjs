const assert = require("node:assert/strict");
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
    conclusion: "【明确规定】证券公司开展该业务应当满足交易商要求。",
    conclusionLabel: "有条件可做",
    productStructure: { underlyingAsset: "", productType: "场外期权", transactionStructure: "", counterparty: "证券公司", investorType: "", isCrossBorder: false, riskPoints: [], missingInfo: [] },
    regulatoryBasis: [{ evidenceId: "chunk_1", title: "伪造标题", publisher: "", url: "https://fake", articleNo: "第一百条", excerpt: "", requirement: "应满足交易商要求", status: "" }],
    restrictions: [], missingInfo: [], manualReviewNote: "", confidenceScore: "medium", confidenceReason: "",
    retrievalTrace: { evidenceHits: 1, clauseHits: 1, documentHits: 1, strategy: "hybrid" },
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

test("端到端服务共用规范化、检索、上下文、回答和引用校验链路", async () => {
  const fakeLlm = { isConfigured: true, chat: async () => JSON.stringify({ conclusion: "【明确规定】应当符合交易商要求。", conclusionLabel: "有条件可做", regulatoryBasis: [{ evidenceId: "chunk_1", requirement: "应符合交易商要求" }], restrictions: ["仅适用于规则覆盖主体"], missingInfo: [], manualReviewNote: "" }) };
  const fakeRetrieval = { search: async () => [hit()] };
  const service = new ComplianceService(fakeLlm, fakeRetrieval, analyzer, new ContextBuilderService(), validator, { getComplianceAgentPrompt: () => "严格执行证据约束" });
  const result = await service.answer("券商可以开展场外期权吗？");
  assert.equal(result.queryAnalysis.productTypes.includes("场外期权"), true);
  assert.equal(result.answer.citationValidation.passed, true);
  assert.equal(result.answer.regulatoryBasis[0].evidenceId, "chunk_1");
});
