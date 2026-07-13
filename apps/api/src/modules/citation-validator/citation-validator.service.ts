import { Injectable } from "@nestjs/common";
import type { ComplianceAnswer, QueryAnalysis, RetrievalHit } from "@otc/shared";

const STRONG_CLAIM = /可以|不可以|必须|应当|不得|禁止|仅限|需要备案|需要报告|适用于|不适用于|已废止|仍然有效|已被替代/;
const CURRENT_STATUS = /现行有效|有效|effective/i;
const INVALID_STATUS = /废止|失效|repealed|invalid/i;
const FUTURE_STATUS = /尚未施行|未生效|将于.{0,20}施行|future/i;

@Injectable()
export class CitationValidatorService {
  validate(
    answer: ComplianceAnswer,
    hits: RetrievalHit[],
    analysis: QueryAnalysis,
    evidenceLevel?: "DIRECT" | "INFERRED" | "INSUFFICIENT",
    assessmentReason = "",
  ): ComplianceAnswer {
    const evidence = new Map(hits.map((hit) => [hit.id, hit]));
    const issues: string[] = [];
    const validBasisRaw = answer.regulatoryBasis.flatMap((basis) => {
      const hit = evidence.get(basis.evidenceId);
      if (!hit) {
        issues.push(`引用的证据ID不存在于本次检索结果: ${basis.evidenceId}`);
        return [];
      }
      const quoteExact = basis.quoteExact || basis.excerpt;
      if (!quoteExact) {
        issues.push(`证据 ${basis.evidenceId} 缺少逐字原文 quoteExact`);
        return [];
      }
      if (!hit.text.includes(quoteExact)) {
        issues.push(`证据 ${basis.evidenceId} 的 quoteExact 不是对应 Chunk 中的连续逐字原文`);
        return [];
      }
      if (analysis.asksValidity && (!hit.status || hit.status === "unknown")) {
        issues.push(`《${hit.title}》效力状态未知，不能据此断言现行有效`);
      }
      if (INVALID_STATUS.test(hit.status) && /现行|当前|仍然有效/.test(answer.conclusion)) {
        issues.push(`《${hit.title}》状态为${hit.status}，不能作为现行依据`);
        return [];
      }
      if (FUTURE_STATUS.test(hit.status) && !/尚未施行|未生效|未来|生效后/.test([
        answer.conclusion,
        answer.scope?.time || "",
        ...answer.restrictions,
      ].join("\n"))) {
        issues.push(`证据 ${basis.evidenceId}《${hit.title}》尚未施行，回答未明确将其限定为未来规则`);
      }
      return [{
        ...basis,
        title: hit.title,
        publisher: hit.publisher,
        url: hit.url,
        articleNo: hit.articleEnd && hit.articleEnd !== hit.articleNo ? `${hit.articleNo}至${hit.articleEnd}` : hit.articleNo,
        excerpt: quoteExact,
        quoteExact,
        status: hit.status,
      }];
    });
    const validBasis = [...validBasisRaw.reduce((grouped, basis) => {
      const key = `${basis.evidenceId}\u0000${basis.quoteExact}`;
      const current = grouped.get(key);
      if (!current) {
        grouped.set(key, basis);
      } else if (basis.requirement && !current.requirement.includes(basis.requirement)) {
        grouped.set(key, { ...current, requirement: `${current.requirement}；${basis.requirement}` });
      }
      return grouped;
    }, new Map<string, (typeof validBasisRaw)[number]>()).values()];

    // A short, non-quantitative exception can be copied deterministically from
    // the already verified quote. This avoids an extra model repair while
    // preserving the source wording. Quantitative exceptions still require a
    // complete model explanation and the stricter checks below.
    const answerBeforeException = [answer.conclusion, ...answer.restrictions, ...(answer.scope?.conditions ?? [])].join("\n");
    const copiedExceptions = validBasis.flatMap((basis) => {
      if (basis.supportRole === "BOUNDARY_ONLY") return [];
      const quote = basis.quoteExact || basis.excerpt;
      if (!/除外|豁免|但书|另有规定/.test(quote) || /除外|例外|豁免|但书/.test(answerBeforeException)) return [];
      if (/\d+(?:\.\d+)?\s*(?:%|万(?:元)?|亿元|元|个月|年|日|倍)/.test(quote)) return [];
      const sentence = quote.split(/(?<=[。；])/).find((part) => /除外|豁免|但书|另有规定/.test(part))?.trim();
      return sentence ? [`原文例外：${sentence}`] : [];
    });
    if (copiedExceptions.length) {
      answer = { ...answer, restrictions: [...new Set([...answer.restrictions, ...copiedExceptions])] };
    }

    const makesBinaryDecision = answer.directAnswer === "是" || answer.directAnswer === "否";
    if (makesBinaryDecision && evidenceLevel && evidenceLevel !== "DIRECT") {
      issues.push(`证据充分性仅为 ${evidenceLevel}，不得生成“是/否”的确定性结论`);
    }
    if ((makesBinaryDecision || STRONG_CLAIM.test(answer.conclusion)) && validBasis.length === 0) issues.push("确定性结论没有对应的有效检索证据");
    if (makesBinaryDecision && validBasis.length > 0 && validBasis.every((basis) => basis.supportRole === "BOUNDARY_ONLY")) {
      issues.push("确定性结论不能仅由说明法规边界的旁证支持");
    }
    if (answer.directAnswer === "不能确认" && answer.conclusionLabel !== "需人工合规复核") {
      issues.push("直接回答为不能确认时，结论标签必须为需人工合规复核");
    }
    if (answer.directAnswer === "是" && answer.conclusionLabel === "不可做") issues.push("直接回答与结论标签相互矛盾");
    if (answer.directAnswer === "否" && answer.conclusionLabel === "可做") issues.push("直接回答与结论标签相互矛盾");
    if (analysis.asksValidity && validBasis.some((basis) => !CURRENT_STATUS.test(basis.status))) {
      issues.push("效力问题缺少可靠的现行有效状态元数据");
    }
    const fullAnswerText = [
      answer.conclusion,
      ...answer.restrictions,
      ...(answer.scope?.conditions ?? []),
    ].join("\n");
    if (/尚未施行|未生效|未来规则|生效后/.test(assessmentReason)) {
      const relevantFutureHit = hits.find((hit) => FUTURE_STATUS.test(hit.status));
      const citedFutureRule = validBasis.some((basis) => FUTURE_STATUS.test(basis.status));
      if (relevantFutureHit && !citedFutureRule) {
        const exceptionReminder = /除外|豁免|但书|另有规定/.test(relevantFutureHit.text)
          ? "；该证据还包含例外或但书，引用时必须在同一次修订中一并完整说明"
          : "";
        issues.push(`证据 ${relevantFutureHit.id}《${relevantFutureHit.title}》已被证据判断识别为相关未来规则，最终回答必须引用并区分其尚未施行的效力状态${exceptionReminder}`);
      }
    }
    if (/无例外|没有例外|不存在例外|一律不设例外/.test(fullAnswerText)) {
      const exceptionBasis = validBasis.find((basis) => /除外|另有规定|但书|豁免/.test(basis.quoteExact || basis.excerpt));
      if (exceptionBasis) {
        issues.push(`证据 ${exceptionBasis.evidenceId} 的原文包含除外或另有规定，回答不得表述为无例外`);
      }
    }
    for (const basis of validBasis) {
      const quote = basis.quoteExact || basis.excerpt;
      if (!/除外|豁免|但书|另有规定/.test(quote)) continue;
      // BOUNDARY_ONLY 只用于说明“现有条文规定到哪里为止”，并不作为
      // 许可、禁止或比例结论的直接依据。把其中另一主体的例外强塞进
      // 当前问题，会制造跨制度噪声；其逐字引文仍保留以便用户核验。
      if (basis.supportRole === "BOUNDARY_ONLY") continue;
      if ((makesBinaryDecision || STRONG_CLAIM.test(answer.conclusion)) && !/除外|例外|豁免|但书/.test(fullAnswerText)) {
        issues.push(`证据 ${basis.evidenceId} 包含例外或豁免条件，回答不得遗漏`);
        continue;
      }
      const quantitativeConditions = [...new Set(
        quote.normalize("NFKC").match(/\d+(?:\.\d+)?\s*(?:%|万(?:元)?|亿元|元|个月|年|日|倍)/g) ?? [],
      )];
      const normalizedAnswer = fullAnswerText.normalize("NFKC").replace(/\s+/g, "");
      const missingConditions = quantitativeConditions.filter((condition) =>
        !normalizedAnswer.includes(condition.replace(/\s+/g, "")),
      );
      if (missingConditions.length && /条件.*(?:除外|例外|豁免)|(?:除外|例外|豁免).*条件/.test(fullAnswerText)) {
        issues.push(`证据 ${basis.evidenceId} 的量化例外条件未完整说明: ${missingConditions.join("、")}`);
      }
    }
    if (issues.length) {
      return {
        ...answer,
        directAnswer: "不能确认",
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
