import { Injectable } from "@nestjs/common";
import type { QueryAnalysis } from "@otc/shared";

const ALIASES: Array<[RegExp, string]> = [
  [/雪球产品?|自动敲入敲出/gi, "雪球（自动赎回场外期权结构）"],
  [/券商/gi, "证券公司"],
  [/收益互换|TRS/gi, "收益互换"],
  [/场外期权|OTC期权/gi, "场外期权"],
  [/适当性|合格投资人/gi, "投资者适当性"],
];

const CONTROLLED_EXPANSIONS: Record<string, string[]> = {
  "雪球": ["敲入", "敲出", "带敲入和敲出结构", "场外期权", "自动赎回", "复杂金融产品", "挂钩标的", "投资者适当性"],
  "场外期权": ["非标准化期权", "期权交易商", "挂钩标的", "风险管理"],
  "收益互换": ["总收益互换", "互换交易", "交易对手", "履约保障"],
  "收益凭证": ["证券公司收益凭证", "发行", "备案", "信息披露", "销售"],
  "适当性": ["投资者适当性", "专业投资者", "合格投资者", "风险承受能力", "风险揭示"],
  "备案": ["备案", "信息报送", "报告义务"],
  "主协议": ["主协议", "补充协议", "交易确认书", "终止净额"],
  "本身标的": ["本公司股票", "期货风险管理公司不得与上市公司", "证券公司不得违规与上市公司", "其发行的股票 合约标的物", "尚未施行"],
  "自身标的": ["本公司股票", "期货风险管理公司不得与上市公司", "证券公司不得违规与上市公司", "其发行的股票 合约标的物", "尚未施行"],
  "私募产品": ["私募证券投资基金", "私募资产管理计划"],
};

const TOPICS: Record<string, RegExp> = {
  "准入": /准入|资格|能否开展|可以开展|可以做|能不能做/,
  "交易": /交易|对手方|主协议|确认书/,
  "销售": /销售|推介|募集/,
  "投资者适当性": /适当性|专业投资者|合格投资者|风险承受/,
  "估值": /估值|定价|公允价值/,
  "风控": /风控|风险管理|保证金|履约保障|净资本/,
  "信息披露": /披露|风险揭示/,
  "备案与报告": /备案|报送|报告/,
  "禁止行为": /禁止|不得|限制/,
  "法律责任": /责任|处罚|违规/,
  "投资比例": /比例|限额|上限|下限|范围/,
  "效力状态": /有效|废止|失效|修订|替代|现行/,
};

const PRODUCTS = ["场外衍生品", "场外期权", "收益互换", "收益凭证", "利率互换", "信用衍生品", "雪球", "远期"];
const SUBJECTS = ["上市公司", "证券公司", "银行", "基金管理人", "私募产品", "私募基金", "私募证券投资基金", "资产管理计划", "期货公司", "风险管理公司", "自然人", "专业投资者", "合格投资者"];
const REGULATORS = ["中国证监会", "国家金融监督管理总局", "中国证券业协会", "中国基金业协会", "中国人民银行", "上交所", "深交所", "银行间市场交易商协会"];

function unique(values: string[]) {
  return [...new Set(values.filter(Boolean))];
}

@Injectable()
export class QueryAnalysisService {
  analyze(originalQuery: string): QueryAnalysis {
    let normalizedQuery = originalQuery.normalize("NFKC").replace(/\s+/g, " ").trim();
    for (const [pattern, replacement] of ALIASES) normalizedQuery = normalizedQuery.replace(pattern, replacement);

    const productTypes = PRODUCTS.filter((value) => normalizedQuery.includes(value));
    const subjects = SUBJECTS.filter((value) => normalizedQuery.includes(value));
    const regulators = REGULATORS.filter((value) => normalizedQuery.includes(value));
    const topics = Object.entries(TOPICS).filter(([, pattern]) => pattern.test(normalizedQuery)).map(([topic]) => topic);
    const keywords = [normalizedQuery, ...productTypes, ...subjects, ...regulators, ...topics];
    for (const [trigger, expansions] of Object.entries(CONTROLLED_EXPANSIONS)) {
      if (normalizedQuery.includes(trigger)) keywords.push(...expansions);
    }

    const clauses = normalizedQuery.split(/[？?；;]|(?:以及|同时|并且|另外|还需要)/).map((part) => part.trim()).filter((part) => part.length >= 6);
    const complex = clauses.length > 1 || topics.length >= 3;
    const subQuestions = complex ? clauses.slice(0, 5) : [normalizedQuery];
    const semanticQueries = unique(subQuestions.map((question) => `${productTypes.join(" ")} ${topics.join(" ")} ${question}`.trim()));
    const year = normalizedQuery.match(/(?:19|20)\d{2}(?:年)?(?:至|到|-)(?:19|20)\d{2}(?:年)?|(?:19|20)\d{2}年?/g)?.join("、") ?? "";

    return {
      originalQuery,
      normalizedQuery,
      legalIssue: topics.length ? topics.join("、") : "场外衍生品监管要求",
      businessTypes: normalizedQuery.includes("场外") || productTypes.length ? ["场外衍生品交易"] : [],
      productTypes,
      subjects,
      regulators,
      timeRange: year,
      asksValidity: TOPICS["效力状态"].test(normalizedQuery),
      topics,
      subQuestions,
      keywords: unique(keywords).slice(0, 30),
      semanticQueries,
    };
  }
}
