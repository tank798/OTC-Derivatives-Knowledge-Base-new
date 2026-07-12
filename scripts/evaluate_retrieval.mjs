#!/usr/bin/env node

import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { env, pipeline } from "@huggingface/transformers";
import {
  MODEL_CACHE,
  MODEL_DTYPE,
  MODEL_ID,
  QUERY_INSTRUCTION,
  ROOT,
  VECTOR_PATH,
  loadIndexArtifacts,
  loadVectorMatrix,
  readJsonl,
  reciprocalRankFusion,
  searchBm25,
  searchVectors,
} from "./retrieval/core.mjs";

const EVAL_DIR = resolve(ROOT, "data/index/eval");
const QUERY_PATH = resolve(EVAL_DIR, "queries.jsonl");

function firstRelevantRank(hits, relevantIds) {
  const relevant = new Set(relevantIds);
  const hit = hits.find((row) => relevant.has(row.chunk_id));
  return hit?.rank ?? null;
}

function summarizeHits(hits, corpus, limit = 10) {
  return hits.slice(0, limit).map((hit) => ({
    rank: hit.rank,
    chunk_id: hit.chunk_id,
    document_title: corpus[hit.index].document_title,
    article_start: corpus[hit.index].article_start,
    article_end: corpus[hit.index].article_end,
    score: hit.rrf ?? hit.bm25 ?? hit.vector ?? 0,
  }));
}

async function main() {
  const cases = readJsonl(QUERY_PATH);
  if (!cases.length) throw new Error("评测集为空");
  const { corpus, manifest, bm25, vectorMetadata } = loadIndexArtifacts();
  const vectors = loadVectorMatrix(VECTOR_PATH, corpus.length, vectorMetadata.dimension);

  env.cacheDir = MODEL_CACHE;
  env.allowRemoteModels = false;
  env.allowLocalModels = true;
  const extractor = await pipeline("feature-extraction", MODEL_ID, {
    dtype: MODEL_DTYPE,
    cache_dir: MODEL_CACHE,
    local_files_only: true,
  });

  const results = [];
  for (const item of cases) {
    const bm25Hits = searchBm25(item.query, corpus, bm25, manifest.fusion.bm25_top_k);
    const embedded = await extractor(`${QUERY_INSTRUCTION}${item.query}`, { pooling: "cls", normalize: true });
    if (embedded.dims.length !== 2 || embedded.dims[1] !== vectorMetadata.dimension) {
      throw new Error(`查询向量维度异常: ${item.id}`);
    }
    const vectorHits = searchVectors(Float32Array.from(embedded.data), vectors, corpus, vectorMetadata.dimension, manifest.fusion.vector_top_k);
    const hybridHits = reciprocalRankFusion(bm25Hits, vectorHits, { k: manifest.fusion.rrf_k, limit: manifest.fusion.fused_top_k });
    const bm25Rank = firstRelevantRank(bm25Hits, item.relevant_chunk_ids);
    const vectorRank = firstRelevantRank(vectorHits, item.relevant_chunk_ids);
    const hybridRank = firstRelevantRank(hybridHits, item.relevant_chunk_ids);
    const passed = Boolean(
      bm25Rank && bm25Rank <= item.bm25_max_rank
      && hybridRank && hybridRank <= item.hybrid_max_rank
    );
    results.push({
      id: item.id,
      query: item.query,
      passed,
      relevant_chunk_ids: item.relevant_chunk_ids,
      thresholds: { bm25_max_rank: item.bm25_max_rank, hybrid_max_rank: item.hybrid_max_rank },
      ranks: { bm25: bm25Rank, vector: vectorRank, hybrid: hybridRank },
      answer_expectation: item.answer_expectation,
      answer_note: item.answer_note,
      top_bm25: summarizeHits(bm25Hits, corpus),
      top_vector: summarizeHits(vectorHits, corpus),
      top_hybrid: summarizeHits(hybridHits, corpus),
    });
  }
  await extractor.dispose?.();

  const passedCount = results.filter((row) => row.passed).length;
  const output = {
    generated_at: new Date().toISOString(),
    corpus: { documents: manifest.corpus.document_count, chunks: manifest.corpus.chunk_count },
    model: { id: vectorMetadata.model_id, revision: vectorMetadata.model_revision, dimension: vectorMetadata.dimension },
    summary: { total: results.length, passed: passedCount, failed: results.length - passedCount },
    results,
  };
  mkdirSync(EVAL_DIR, { recursive: true });
  writeFileSync(resolve(EVAL_DIR, "results.json"), JSON.stringify(output, null, 2) + "\n", "utf8");
  const lines = [
    "# 检索评测结果", "",
    `- 语料：${output.corpus.documents} 份法规 / ${output.corpus.chunks} 个 Chunk`,
    `- 结果：${passedCount}/${results.length} 通过`, "",
    "| 问题 | BM25最佳相关排名 | 向量最佳相关排名 | RRF最佳相关排名 | 结果 | 回答期望 |",
    "|---|---:|---:|---:|---|---|",
    ...results.map((row) => `| ${row.query} | ${row.ranks.bm25 ?? "-"} | ${row.ranks.vector ?? "-"} | ${row.ranks.hybrid ?? "-"} | ${row.passed ? "PASS" : "FAIL"} | ${row.answer_expectation} |`),
    "",
  ];
  writeFileSync(resolve(EVAL_DIR, "results.md"), lines.join("\n"), "utf8");
  console.log(JSON.stringify(output.summary, null, 2));
  if (passedCount !== results.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
