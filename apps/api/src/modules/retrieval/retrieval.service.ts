import { Injectable, OnModuleInit } from "@nestjs/common";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import type { QueryAnalysis, RetrievalHit } from "@otc/shared";

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

  async search(analysis: QueryAnalysis, limit = 14): Promise<RetrievalHit[]> {
    if (!this.isReady) throw new Error("知识库索引尚未加载完成");
    const keywordQueries = [...analysis.subQuestions, analysis.keywords.join(" ")].filter(Boolean);
    const semanticQueries = analysis.semanticQueries.length ? analysis.semanticQueries : [analysis.normalizedQuery];
    const bm25Hits = this.mergeChannel(keywordQueries.map((query) => this.core.searchBm25(query, this.corpus, this.bm25, 30)), "bm25");

    let vectorHits: RankedHit[] = [];
    try {
      const lists: RankedHit[][] = [];
      for (const query of semanticQueries) {
        const queryVector = await this.embedQuery(query);
        lists.push(this.core.searchVectors(queryVector, this.vectors!, this.corpus, this.core.MODEL_DIMENSION, 30));
      }
      vectorHits = this.mergeChannel(lists, "vector");
    } catch (error) {
      console.warn(`[Retrieval] 向量检索不可用，当前请求仅返回BM25结果: ${error instanceof Error ? error.message : error}`);
    }

    let fused = this.core.reciprocalRankFusion(bm25Hits, vectorHits, { k: 60, limit: 30 });
    fused = this.prependExactMatches(analysis.normalizedQuery, fused);
    const evidence = this.core.assembleEvidence(fused, this.corpus, { limit, maxWithContext: limit });
    const maxRrf = Math.max(...fused.map((hit) => hit.rrf), 1 / 61);

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
      } satisfies RetrievalHit;
    });
  }

  private mergeChannel(lists: RankedHit[][], field: "bm25" | "vector") {
    const best = new Map<string, RankedHit>();
    for (const list of lists) {
      for (const hit of list) {
        const current = best.get(hit.chunk_id);
        if (!current || hit.rank < current.rank) best.set(hit.chunk_id, hit);
      }
    }
    return [...best.values()].sort((a, b) => a.rank - b.rank || (b[field] ?? 0) - (a[field] ?? 0)).slice(0, 30).map((hit, index) => ({ ...hit, rank: index + 1 }));
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
