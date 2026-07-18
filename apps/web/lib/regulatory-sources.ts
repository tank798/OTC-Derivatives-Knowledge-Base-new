import type { AgentRegulatoryAnswer, AgentRegulatoryBasis, RetrievalHit } from "@otc/shared";

export type RegulatorySourceChunk = {
  evidenceId: string;
  articleLabel: string;
  text: string;
  hasCompleteChunk: boolean;
};

export type RegulatorySourceDocument = {
  key: string;
  title: string;
  publisher: string;
  documentNumber: string;
  status: string;
  url: string;
  chunks: RegulatorySourceChunk[];
};

export function groupRegulatorySources(
  answer: AgentRegulatoryAnswer | undefined,
  hits: RetrievalHit[],
): RegulatorySourceDocument[] {
  const hitByEvidenceId = new Map(hits.map((hit) => [hit.id, hit]));
  const groups = new Map<string, RegulatorySourceDocument>();

  for (const basis of answer?.regulatoryBasis ?? []) {
    const hit = hitByEvidenceId.get(basis.evidenceId);
    const key = hit?.documentId || fallbackDocumentKey(basis);
    const group = groups.get(key) ?? {
      key,
      title: hit?.title || basis.title,
      publisher: hit?.publisher || basis.publisher,
      documentNumber: hit?.documentNumber || basis.documentNumber,
      status: hit?.status || basis.status,
      url: hit?.url || basis.url,
      chunks: [],
    };

    if (!group.chunks.some((chunk) => chunk.evidenceId === basis.evidenceId)) {
      group.chunks.push({
        evidenceId: basis.evidenceId,
        articleLabel: articleRange(hit, basis),
        text: hit?.text || basis.quoteExact,
        hasCompleteChunk: Boolean(hit?.text),
      });
    }

    groups.set(key, group);
  }

  return [...groups.values()];
}

function fallbackDocumentKey(basis: AgentRegulatoryBasis) {
  return [basis.title, basis.documentNumber, basis.url].join("|");
}

function articleRange(hit: RetrievalHit | undefined, basis: AgentRegulatoryBasis) {
  const start = hit?.articleNo?.trim();
  const end = hit?.articleEnd?.trim();
  if (start && end && start !== end) return `${start}至${end}`;
  return start || basis.articleNo;
}
