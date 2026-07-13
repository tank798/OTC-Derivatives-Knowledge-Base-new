import { Injectable, OnModuleInit } from "@nestjs/common";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import type { AgentProgressEvent, HybridSearchInput, RetrievalHit } from "@otc/shared";

type CoreModule = {
  MODEL_CACHE: string;
  MODEL_DIMENSION: number;
  MODEL_DTYPE: string;
  MODEL_ID: string;
  MODEL_REVISION: string;
  QUERY_INSTRUCTION: string;
  VECTOR_PATH: string;
  assembleEvidence: (hits: unknown[], corpus: CorpusRow[], options: object) => CorpusRow[];
  loadIndexArtifacts: () => { corpus: CorpusRow[]; manifest: any; bm25: any; vectorMetadata: any };
  loadVectorMatrix: (path: string, count: number, dimension: number) => Float32Array;
  normalizeTitle: (value: string) => string;
  reciprocalRankFusion: (bm25: RankedHit[], vector: RankedHit[], options: object) => FusedHit[];
  searchBm25: (query: string, corpus: CorpusRow[], index: any, limit: number) => RankedHit[];
  searchVectors: (query: Float32Array, matrix: Float32Array, corpus: CorpusRow[], dimension: number, limit: number) => RankedHit[];
};

type CorpusRow = Record<string, any> & { chunk_id: string; document_id: string; text: string; document_title: string };
type RankedHit = { chunk_id: string; index: number; rank: number; bm25?: number; vector?: number };
type FusedHit = RankedHit & { rrf: number; bm25_rank?: number | null; vector_rank?: number | null };
type ProgressCallback = (event: AgentProgressEvent) => void;

const dynamicImport = new Function("specifier", "return import(specifier)") as (specifier: string) => Promise<any>;

@Injectable()
export class RetrievalService implements OnModuleInit {
  isReady = false;
  private root = "";
  private core!: CoreModule;
  private corpus: CorpusRow[] = [];
  private manifest: any = null;
  private bm25: any = null;
  private vectorMetadata: any = null;
  private vectors: Float32Array | null = null;
  private extractor: any = null;

  async onModuleInit() {
    this.root = this.findRepoRoot();
    this.core = await dynamicImport(pathToFileURL(resolve(this.root, "scripts/retrieval/core.mjs")).href);
    const artifacts = this.core.loadIndexArtifacts();
    this.corpus = artifacts.corpus;
    this.manifest = artifacts.manifest;
    this.bm25 = artifacts.bm25;
    this.vectorMetadata = artifacts.vectorMetadata;
    this.vectors = this.core.loadVectorMatrix(this.core.VECTOR_PATH, this.corpus.length, this.core.MODEL_DIMENSION);
    this.isReady = true;
  }

  get stats() {
    return {
      documents: this.manifest?.corpus?.document_count ?? 0,
      chunks: this.corpus.length,
      bm25Ready: Boolean(this.bm25),
      vectorsReady: Boolean(this.vectors),
      embeddingModelCached: existsSync(resolve(this.core?.MODEL_CACHE ?? "", this.core?.MODEL_ID ?? "")),
      legacyClausesEnabled: false,
    };
  }

  async hybridSearch(input: HybridSearchInput, onProgress?: ProgressCallback): Promise<RetrievalHit[]> {
    if (!this.isReady) throw new Error("知识库索引尚未加载完成");
    const { keywordQueries, semanticQueries } = this.buildChannelQueries(input);
    onProgress?.({ id: "bm25", label: "正在进行 BM25 关键词排序", status: "running" });
    const bm25Hits = this.mergeChannel(keywordQueries.map((query) => this.core.searchBm25(query, this.corpus, this.bm25, 30)), "bm25");
    onProgress?.({ id: "bm25", label: "BM25 关键词排序完成", status: "done", detail: `${bm25Hits.length} 个候选 Chunk` });

    let vectorHits: RankedHit[] = [];
    onProgress?.({ id: "vector", label: "正在进行向量语义排序", status: "running" });
    try {
      const lists: RankedHit[][] = [];
      for (const query of semanticQueries) {
        const queryVector = await this.embedQuery(query);
        lists.push(this.core.searchVectors(queryVector, this.vectors!, this.corpus, this.core.MODEL_DIMENSION, 30));
      }
      vectorHits = this.mergeChannel(lists, "vector");
      onProgress?.({ id: "vector", label: "向量语义排序完成", status: "done", detail: `${vectorHits.length} 个候选 Chunk` });
    } catch (error) {
      console.warn(`[Retrieval] 向量检索不可用，当前请求仅返回BM25结果: ${error instanceof Error ? error.message : error}`);
      onProgress?.({ id: "vector", label: "向量排序不可用，已使用关键词结果", status: "done" });
    }

    onProgress?.({ id: "rrf", label: "正在融合两路检索结果", status: "running" });
    let fused = this.core.reciprocalRankFusion(bm25Hits, vectorHits, { k: 60, limit: 30 });
    fused = this.prependExactMatches(input.queries.join(" "), fused);
    const evidence = this.core.assembleEvidence(fused, this.corpus, { limit: input.topK, maxWithContext: input.topK });
    const maxRrf = Math.max(...fused.map((hit) => hit.rrf), 1 / 61);
    const rrfRanks = new Map(fused.map((hit, index) => [hit.chunk_id, index + 1]));
    onProgress?.({ id: "rrf", label: "混合检索结果已整理", status: "done", detail: `${evidence.length} 个法规 Chunk` });

    return evidence.map((row: any) => {
      const retrieval = row.retrieval as FusedHit | null;
      const methods = [retrieval?.bm25_rank ? "bm25" : "", retrieval?.vector_rank ? "vector" : "", retrieval ? "rrf" : "context"].filter(Boolean);
      return {
        source: "chunk",
        id: row.chunk_id,
        documentId: row.document_id,
        chunkId: row.chunk_id,
        title: row.document_title,
        publisher: row.issuing_authority || "",
        url: row.official_url || "",
        publishedAt: row.publication_date || "",
        effectiveAt: row.effective_date || "",
        articleNo: row.article_start || "",
        articleEnd: row.article_end || "",
        chapterTitle: [row.part_title, row.chapter_title, row.section_title].filter(Boolean).join(" / "),
        documentNumber: row.document_number || "",
        text: row.text,
        excerpt: row.text.slice(0, 500),
        score: retrieval ? Math.min(1, retrieval.rrf / maxRrf) : 0,
        authorityLevel: "",
        status: row.validity_status || "unknown",
        verificationStatus: row.validity_status ? "metadata" : "效力状态待核验",
        matchReason: methods.join(" + "),
        retrievalMethods: methods,
        localFilePath: row.local_file_path || "",
        bm25Rank: retrieval?.bm25_rank ?? null,
        vectorRank: retrieval?.vector_rank ?? null,
        rrfRank: retrieval ? (rrfRanks.get(row.chunk_id) ?? null) : null,
        isSupplementalContext: !retrieval,
        subQuestion: input.subQuestion,
      } satisfies RetrievalHit;
    });
  }

  private mergeChannel(lists: RankedHit[][], field: "bm25" | "vector") {
    const queues = lists.map((list) => [...list]);
    const seen = new Set<string>();
    const balanced: RankedHit[] = [];

    // Scores from different queries are not comparable. Interleave their
    // ranked lists so a direct-rule query issued later cannot be crowded out
    // by several broad queries with larger raw BM25/cosine values.
    while (balanced.length < 30 && queues.some((queue) => queue.length)) {
      for (const queue of queues) {
        while (queue.length) {
          const hit = queue.shift()!;
          if (seen.has(hit.chunk_id)) continue;
          seen.add(hit.chunk_id);
          balanced.push(hit);
          break;
        }
        if (balanced.length >= 30) break;
      }
    }
    return balanced.map((hit, index) => ({ ...hit, rank: index + 1 }));
  }

  private expandScopeTerms(terms: string[]) {
    const expanded = new Set(terms.filter(Boolean));
    for (const term of expanded) {
      if (/期货公司.*风险管理.*(?:子公司|公司)/.test(term)) {
        expanded.add("期货风险管理公司");
        expanded.add("风险管理公司");
      }
    }
    return [...expanded];
  }

  private buildChannelQueries(input: HybridSearchInput) {
    const scopedTerms = this.expandScopeTerms([
      ...input.subjects,
      ...input.productTypes,
      ...input.counterparties,
    ]).join(" ");
    const scopedQuery = `${scopedTerms} ${input.subQuestion}`.trim();
    const keywordQueries = [...new Set([...input.queries, scopedQuery].filter(Boolean))];
    const semanticQueries = [...new Set([
      ...input.queries.map((query) => `${input.subQuestion} ${query}`.trim()),
      scopedQuery,
    ].filter(Boolean))];
    return { keywordQueries, semanticQueries };
  }

  private prependExactMatches(query: string, fused: FusedHit[]) {
    const normalizedQuery = this.core.normalizeTitle(query);
    const exact = this.corpus.map((row, index) => ({ row, index })).filter(({ row }) => {
      const title = this.core.normalizeTitle(row.document_title);
      const number = this.core.normalizeTitle(row.document_number || "");
      return (title.length >= 6 && normalizedQuery.includes(title)) || (number && normalizedQuery.includes(number));
    });
    const exactIds = new Set(exact.map(({ row }) => row.chunk_id));
    const anchors = exact.slice(0, 3).map(({ row, index }, rank) => ({ chunk_id: row.chunk_id, index, rank: rank + 1, rrf: 1, bm25_rank: 1, vector_rank: null }));
    return [...anchors, ...fused.filter((hit) => !exactIds.has(hit.chunk_id))];
  }

  private async embedQuery(query: string): Promise<Float32Array> {
    if (!this.extractor) {
      const transformers = await dynamicImport("@huggingface/transformers");
      transformers.env.cacheDir = this.core.MODEL_CACHE;
      transformers.env.allowRemoteModels = false;
      transformers.env.allowLocalModels = true;
      this.extractor = await transformers.pipeline("feature-extraction", this.core.MODEL_ID, {
        dtype: this.core.MODEL_DTYPE,
        cache_dir: this.core.MODEL_CACHE,
        local_files_only: true,
      });
    }
    const output = await this.extractor(`${this.core.QUERY_INSTRUCTION}${query}`, { pooling: "cls", normalize: true });
    return new Float32Array(output.data);
  }

  private findRepoRoot() {
    let current = process.cwd();
    for (let depth = 0; depth < 12; depth += 1) {
      if (existsSync(resolve(current, "data/index/manifest.json"))) return current;
      const parent = resolve(current, "..");
      if (parent === current) break;
      current = parent;
    }
    throw new Error("Cannot find project root containing data/index/manifest.json");
  }
}
