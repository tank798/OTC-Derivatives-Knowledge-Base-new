import { Injectable } from "@nestjs/common";
import type {
  AgentAnswerDraft,
  AgentRegulatoryAnswer,
  AgentRegulatoryBasis,
  RetrievalHit,
} from "@otc/shared";

export type CitationValidationResult = {
  answer: AgentRegulatoryAnswer;
  issues: string[];
};

const FORMATTING_PUNCTUATION = new Set([
  ",", "，", ".", "。", ";", "；", ":", "：", "!", "！", "?", "？",
  "\"", "'", "“", "”", "‘", "’", "(", ")", "（", "）", "[", "]",
  "【", "】", "{", "}", "《", "》", "〈", "〉", "「", "」", "『", "』",
  "、", "…", "·",
]);

const INSUFFICIENT_CONCLUSION = /(?:无法|不能|不足|未能|尚无|没有).{0,16}(?:确定|判断|得出|支持|证据|规定|结论)|证据不足/u;

/**
 * 只做可确定的引用真实性检查。
 *
 * 这里故意不评判法律结论是否正确，也不评判某条证据是否“足以”
 * 支持结论。它只确认：evidenceId 来自本次上下文，逐字引文属于该
 * Chunk，并由该 Chunk 回填真实的法规名称、机关、条号和链接。
 */
@Injectable()
export class CitationValidatorService {
  validateDraft(draft: AgentAnswerDraft, hits: RetrievalHit[]): CitationValidationResult {
    const evidence = new Map(hits.map((hit) => [hit.id, hit]));
    const issues: string[] = [];
    const validBasis: AgentRegulatoryBasis[] = [];
    const seen = new Set<string>();

    if (draft.regulatoryBasis.length === 0) {
      if (!INSUFFICIENT_CONCLUSION.test(draft.conclusion)) {
        issues.push("确定性法规结论至少需要一条通过真实性校验的法规依据");
      }
    }

    for (const [index, basis] of draft.regulatoryBasis.entries()) {
      const position = `第 ${index + 1} 条引用`;
      const hit = evidence.get(basis.evidenceId);
      if (!hit) {
        issues.push(`${position}的 evidenceId 不在本次提供给 Agent 的 Chunk 上下文中: ${basis.evidenceId}`);
        continue;
      }
      const sourceQuote = this.findSourceQuote(hit.text, basis.quoteExact);
      if (!sourceQuote) {
        issues.push(`${position}的 quoteExact 不是 ${basis.evidenceId} 中的连续逐字原文`);
        continue;
      }

      const key = `${basis.evidenceId}\u0000${sourceQuote}`;
      if (seen.has(key)) continue;
      seen.add(key);

      validBasis.push({
        evidenceId: hit.id,
        title: hit.title,
        publisher: hit.publisher,
        documentNumber: hit.documentNumber,
        articleNo: hit.articleEnd && hit.articleEnd !== hit.articleNo
          ? `${hit.articleNo}至${hit.articleEnd}`
          : hit.articleNo,
        status: hit.status,
        url: hit.url,
        quoteExact: sourceQuote,
        explanation: basis.explanation,
      });
    }

    if (draft.regulatoryBasis.length > 0 && validBasis.length === 0 && issues.length === 0) {
      issues.push("提交的法规依据均未通过真实性校验");
    }

    return {
      issues,
      answer: {
        conclusion: draft.conclusion,
        reasoningSummary: draft.reasoningSummary,
        regulatoryBasis: validBasis,
        wikiBasis: [],
        missingInformation: draft.missingInformation,
        manualReviewNote: draft.manualReviewNote,
        citationValidation: { passed: issues.length === 0, issues },
      },
    };
  }

  /**
   * 优先要求逐字命中。若模型只改变了空白、Markdown 标记或不承载
   * 法律含义的排版标点，则按文字内容在原文中唯一对齐，并回填原文
   * 中的真实连续片段。数字、百分号、金额、日期、运算符、主体名称
   * 和正文字符都不能被忽略或改写。
   */
  private findSourceQuote(source: string, proposedQuote: string) {
    if (!proposedQuote) return null;
    if (source.includes(proposedQuote)) return proposedQuote;

    const proposed = this.canonicalCharacters(proposedQuote);
    if (proposed.length < 12) return null;
    const sourceCharacters = this.canonicalCharacters(source, true);
    const sourceCanonical = sourceCharacters.map((entry) => entry.character).join("");
    const proposedCanonical = proposed.map((entry) => entry.character).join("");
    const start = sourceCanonical.indexOf(proposedCanonical);
    if (start < 0 || sourceCanonical.indexOf(proposedCanonical, start + 1) >= 0) return null;

    const first = sourceCharacters[start];
    const last = sourceCharacters[start + proposedCanonical.length - 1];
    if (!first || !last) return null;
    return source.slice(first.start, last.end).trim();
  }

  private canonicalCharacters(value: string, preservePositions = false) {
    const entries: Array<{ character: string; start: number; end: number }> = [];

    for (let index = 0; index < value.length;) {
      const codePoint = value.codePointAt(index);
      if (codePoint === undefined) break;
      const original = String.fromCodePoint(codePoint);
      const start = index;
      index += original.length;

      const normalized = original.normalize("NFKC").toLowerCase();
      for (const character of normalized) {
        if (this.isIgnorableFormattingCharacter(value, start, index, character)) continue;
        entries.push({
          character,
          start: preservePositions ? start : 0,
          end: preservePositions ? index : 0,
        });
      }
    }
    return entries;
  }

  private isIgnorableFormattingCharacter(
    value: string,
    start: number,
    end: number,
    character: string,
  ) {
    if (/\s/u.test(character) || ["*", "_", "`", "~"].includes(character)) return true;

    if (!FORMATTING_PUNCTUATION.has(character)) return false;

    // 小数点、千分位逗号和时间冒号位于数字之间时具有实质含义。
    if ([".", ",", ":"].includes(character)) {
      const previous = value.slice(0, start).match(/\S(?=\s*$)/u)?.[0] ?? "";
      const next = value.slice(end).match(/^\s*(\S)/u)?.[1] ?? "";
      if (/\d/u.test(previous) && /\d/u.test(next)) return false;
    }
    return true;
  }
}
