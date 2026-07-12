import { Injectable } from "@nestjs/common";
import type { ComplianceAnswer, QueryAnalysis, RetrievalHit } from "@otc/shared";

const STRONG_CLAIM = /可以|不可以|必须|应当|不得|禁止|仅限|需要备案|需要报告|适用于|不适用于|已废止|仍然有效|已被替代/;
const CURRENT_STATUS = /现行有效|有效|effective/i;
const INVALID_STATUS = /废止|失效|repealed|invalid/i;

function directEvidenceIssue(answer: ComplianceAnswer, analysis: QueryAnalysis, hits: RetrievalHit[]): string {
  const query = analysis.normalizedQuery;
  const texts = hits.map((hit) => hit.text.replace(/\s+/g, ""));
  const asksOwnUnderlying = /(自己|自身|本身|本公司).{0,10}(标的|股票)/.test(query);
  if (asksOwnUnderlying) {
    const direct = texts.some((text) => /(自身|本公司|其发行的股票).{0,24}(场外衍生品|场外期权|挂钩标的|合约标的|衍生品交易)|(场外衍生品|场外期权|挂钩标的|合约标的|衍生品交易).{0,24}(自身|本公司|其发行的股票)/.test(text));
    if (!direct) return "未检索到上市公司以本公司股票为场外衍生品挂钩标的的直接规定";
    const hasCurrentCounterpartyBan = hits.some((hit) => /(?:期货)?风险管理公司不得与上市公司/.test(hit.text));
    const hasFutureGeneralBan = hits.some((hit) => /尚未施行|未生效/.test(hit.status) && /上市公司.*不得达成.*其发行的股票/.test(hit.text.replace(/\s+/g, "")));
    if (/可以|可做|有条件可做/.test(answer.conclusion)) {
      if (hasCurrentCounterpartyBan && !/期货风险管理公司|交易对手/.test(answer.conclusion)) {
        return "可行性结论未限定现行规则已禁止的期货风险管理公司交易路径";
      }
      if (hasFutureGeneralBan && !/尚未施行|未生效|生效|未来/.test(answer.conclusion)) {
        return "可行性结论未区分已公布尚未施行的更广泛禁止规则及其生效时点";
      }
    }
  }
  const asksVoucherSnowball = /收益凭证.*雪球|雪球.*收益凭证/.test(query);
  if (asksVoucherSnowball) {
    const direct = hits.some((hit) => hit.title.includes("证券公司收益凭证发行管理办法") && /(雪球|敲入|敲出)/.test(hit.text));
    if (!direct) return "收益凭证通用发行规则未直接列明雪球结构，不足以对具体产品作无条件的可行性结论";
  }
  return "";
}

@Injectable()
export class CitationValidatorService {
  validate(answer: ComplianceAnswer, hits: RetrievalHit[], analysis: QueryAnalysis): ComplianceAnswer {
    const evidence = new Map(hits.map((hit) => [hit.id, hit]));
    const issues: string[] = [];
    const validBasis = answer.regulatoryBasis.flatMap((basis) => {
      const hit = evidence.get(basis.evidenceId);
      if (!hit) {
        issues.push(`引用的证据ID不存在于本次检索结果: ${basis.evidenceId}`);
        return [];
      }
      if (analysis.asksValidity && (!hit.status || hit.status === "unknown")) {
        issues.push(`《${hit.title}》效力状态未知，不能据此断言现行有效`);
      }
      if (INVALID_STATUS.test(hit.status) && /现行|当前|仍然有效/.test(answer.conclusion)) {
        issues.push(`《${hit.title}》状态为${hit.status}，不能作为现行依据`);
        return [];
      }
      return [{
        ...basis,
        title: hit.title,
        publisher: hit.publisher,
        url: hit.url,
        articleNo: hit.articleEnd && hit.articleEnd !== hit.articleNo ? `${hit.articleNo}至${hit.articleEnd}` : hit.articleNo,
        excerpt: hit.excerpt || hit.text.slice(0, 500),
        status: hit.status,
      }];
    });

    if (STRONG_CLAIM.test(answer.conclusion) && validBasis.length === 0) issues.push("强结论没有对应的有效检索证据");
    if (analysis.asksValidity && validBasis.some((basis) => !CURRENT_STATUS.test(basis.status))) {
      issues.push("效力问题缺少可靠的现行有效状态元数据");
    }
    const directIssue = directEvidenceIssue(answer, analysis, hits);
    if (directIssue && STRONG_CLAIM.test(answer.conclusion)) issues.push(directIssue);

    if (issues.length) {
      return {
        ...answer,
        conclusion: "【证据不足】根据当前知识库检索结果，暂时无法形成确定结论。",
        conclusionLabel: "需人工合规复核",
        regulatoryBasis: validBasis,
        missingInfo: [...new Set([...answer.missingInfo, ...issues])],
        manualReviewNote: "已检索到的片段不足以支持确定性法律结论，请补充直接规定、可靠效力状态或具体业务事实后复核。",
        confidenceScore: "low",
        confidenceReason: issues.join("；"),
        citationValidation: { passed: false, issues },
      };
    }
    return { ...answer, regulatoryBasis: validBasis, citationValidation: { passed: true, issues: [] } };
  }
}
