export declare const COMPLIANCE_CONCLUSION: {
    readonly CAN_DO: "可做";
    readonly CANNOT_DO: "不可做";
    readonly CONDITIONAL: "有条件可做";
    readonly NEED_MANUAL_REVIEW: "需人工合规复核";
};
export type ComplianceConclusion = (typeof COMPLIANCE_CONCLUSION)[keyof typeof COMPLIANCE_CONCLUSION];
export declare const REGULATOR_ENTITY: {
    readonly SECURITIES_COMPANY: "证券公司";
    readonly FUTURES_COMPANY: "期货公司";
    readonly FUND_COMPANY: "基金管理公司";
    readonly PRIVATE_FUND: "私募基金管理人";
    readonly BANK: "商业银行";
    readonly TRUST_COMPANY: "信托公司";
    readonly INSURANCE_COMPANY: "保险公司";
    readonly PROFESSIONAL_INVESTOR: "专业机构投资者";
    readonly RETAIL_INVESTOR: "普通个人投资者";
    readonly QUALIFIED_INVESTOR: "合格投资者";
};
export declare const PRODUCT_CATEGORY: {
    readonly SWAP: "收益互换";
    readonly FORWARD: "远期";
    readonly NON_STANDARD_OPTION: "场外期权";
    readonly STRUCTURED_NOTE: "结构化票据";
    readonly INCOME_CERTIFICATE: "收益凭证";
    readonly ASSET_MANAGEMENT_PLAN: "资管计划";
    readonly PRIVATE_FUND: "私募基金";
    readonly CREDIT_PROTECTION: "信用保护工具";
    readonly CRM: "信用风险缓释工具";
    readonly FX_DERIVATIVE: "外汇衍生品";
    readonly REPO: "回购";
};
export declare const ANSWER_MESSAGE_TYPE: {
    readonly COMPLIANCE_ANSWER: "compliance_answer";
    readonly CLARIFICATION: "clarification";
    readonly OUT_OF_SCOPE: "out_of_scope";
};
export type AnswerMessageType = (typeof ANSWER_MESSAGE_TYPE)[keyof typeof ANSWER_MESSAGE_TYPE];
//# sourceMappingURL=enums.d.ts.map