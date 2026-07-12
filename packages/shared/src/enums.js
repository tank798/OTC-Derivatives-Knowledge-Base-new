"use strict";
// ────────── 产品结构 & 合规分类 ──────────
Object.defineProperty(exports, "__esModule", { value: true });
exports.ANSWER_MESSAGE_TYPE = exports.PRODUCT_CATEGORY = exports.REGULATOR_ENTITY = exports.COMPLIANCE_CONCLUSION = void 0;
exports.COMPLIANCE_CONCLUSION = {
    CAN_DO: "可做",
    CANNOT_DO: "不可做",
    CONDITIONAL: "有条件可做",
    NEED_MANUAL_REVIEW: "需人工合规复核",
};
exports.REGULATOR_ENTITY = {
    SECURITIES_COMPANY: "证券公司",
    FUTURES_COMPANY: "期货公司",
    FUND_COMPANY: "基金管理公司",
    PRIVATE_FUND: "私募基金管理人",
    BANK: "商业银行",
    TRUST_COMPANY: "信托公司",
    INSURANCE_COMPANY: "保险公司",
    PROFESSIONAL_INVESTOR: "专业机构投资者",
    RETAIL_INVESTOR: "普通个人投资者",
    QUALIFIED_INVESTOR: "合格投资者",
};
exports.PRODUCT_CATEGORY = {
    SWAP: "收益互换",
    FORWARD: "远期",
    NON_STANDARD_OPTION: "场外期权",
    STRUCTURED_NOTE: "结构化票据",
    INCOME_CERTIFICATE: "收益凭证",
    ASSET_MANAGEMENT_PLAN: "资管计划",
    PRIVATE_FUND: "私募基金",
    CREDIT_PROTECTION: "信用保护工具",
    CRM: "信用风险缓释工具",
    FX_DERIVATIVE: "外汇衍生品",
    REPO: "回购",
};
exports.ANSWER_MESSAGE_TYPE = {
    COMPLIANCE_ANSWER: "compliance_answer",
    CLARIFICATION: "clarification",
    OUT_OF_SCOPE: "out_of_scope",
};
//# sourceMappingURL=enums.js.map