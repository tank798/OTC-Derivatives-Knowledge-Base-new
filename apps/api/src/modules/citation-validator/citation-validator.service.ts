import { Injectable } from "@nestjs/common";
import type { ComplianceAnswer, QueryAnalysis, RetrievalHit } from "@otc/shared";

const STRONG_CLAIM = /可以|不可以|必须|应当|不得|禁止|仅限|需要备案|需要报告|适用于|不适用于|已废止|仍然有效|已被替代/;
const CURRENT_STATUS = /现行有效|有效|effective/i;
const INVALID_STATUS = /废止|失效|repealed|invalid/i;

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
        articleNo: hit.articleNo,
        excerpt: hit.excerpt || hit.text.slice(0, 500),
        status: hit.status,
      }];
    });

    if (STRONG_CLAIM.test(answer.conclusion) && validBasis.length === 0) issues.push("强结论没有对应的有效检索证据");
    if (analysis.asksValidity && validBasis.some((basis) => !CURRENT_STATUS.test(basis.status))) {
      issues.push("效力问题缺少可靠的现行有效状态元数据");
    }

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
