#!/usr/bin/env node

import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  BM25_PATH,
  MODEL_CACHE,
  MODEL_DTYPE,
  MODEL_ID,
  QUERY_INSTRUCTION,
  VECTOR_PATH,
  assembleEvidence,
  buildBm25,
  buildDocumentCorpus,
  diversifyByDocument,
  fuseAdditionalRankedChannel,
  loadIndexArtifacts,
  loadVectorMatrix,
  mapDocumentHitsToChunkAnchors,
  reciprocalRankFusion,
  searchBm25,
  searchVectors,
} from "./retrieval/core.mjs";

function parseArgs(argv) {
  const options = { query: "", json: false, evidenceLimit: 10 };
  const queryParts = [];
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--json") options.json = true;
    else if (argv[index] === "--limit") options.evidenceLimit = Number(argv[++index] ?? 10);
    else queryParts.push(argv[index]);
  }
  options.query = queryParts.join(" ").trim();
  return options;
}

async function embedQuery(query, dimension) {
  const { env, pipeline } = await import("@huggingface/transformers");
  env.cacheDir = MODEL_CACHE;
  env.allowRemoteModels = false;
  const extractor = await pipeline("feature-extraction", MODEL_ID, {
    dtype: MODEL_DTYPE,
    cache_dir: MODEL_CACHE,
    local_files_only: true,
  });
  const output = await extractor(QUERY_INSTRUCTION + query, { pooling: "cls", normalize: true });
  if (output.dims.length !== 2 || output.dims[1] !== dimension) {
    throw new Error(`查询Embedding维度异常: ${JSON.stringify(output.dims)}`);
  }
  const vector = Float32Array.from(output.data);
  await extractor.dispose?.();
  return vector;
}

export async function hybridSearch(query, options = {}) {
  const { corpus, manifest, bm25, vectorMetadata } = loadIndexArtifacts();
  const bm25TopK = options.bm25TopK ?? manifest.fusion.bm25_top_k;
  const vectorTopK = options.vectorTopK ?? manifest.fusion.vector_top_k;
  const fusedTopK = options.fusedTopK ?? Math.max(30, manifest.fusion.fused_top_k);
  const bm25FullHits = searchBm25(query, corpus, bm25, corpus.length);
  const bm25Hits = bm25FullHits.slice(0, bm25TopK);
  const documentCorpus = buildDocumentCorpus(corpus);
  const documentHits = searchBm25(query, documentCorpus, buildBm25(documentCorpus), 12);
  const queryVector = await embedQuery(query, vectorMetadata.dimension);
  const matrix = loadVectorMatrix(VECTOR_PATH, corpus.length, vectorMetadata.dimension);
  const vectorHits = searchVectors(queryVector, matrix, corpus, vectorMetadata.dimension, vectorTopK);
  const fusedHits = diversifyByDocument(
    fuseAdditionalRankedChannel(
      reciprocalRankFusion(bm25Hits, vectorHits, { k: manifest.fusion.rrf_k, limit: bm25TopK + vectorTopK }),
      mapDocumentHitsToChunkAnchors(
        documentHits,
        [bm25FullHits],
        documentCorpus,
        corpus,
        { maxPerDocument: 1 },
      ),
      { k: manifest.fusion.rrf_k, limit: fusedTopK, weight: 1, rankField: "document_rank" },
    ),
    corpus,
    { maxPerDocument: 2 },
  );
  const evidenceLimit = options.evidenceLimit ?? 10;
  const evidence = assembleEvidence(fusedHits, corpus, { limit: evidenceLimit, maxWithContext: evidenceLimit });
  return {
    query,
    strategy: "Chunk BM25 + document BM25 + BGE-base-zh-v1.5 + RRF",
    corpus: { documents: manifest.corpus.document_count, chunks: manifest.corpus.chunk_count },
    retrieval: { bm25_top_k: bm25TopK, vector_top_k: vectorTopK, fused_top_k: fusedTopK },
    evidence_policy: "文档级适用性与Chunk级关键词/向量相关性融合；正文去重并按需补充重叠来源/前置条款",
    fused_hits: fusedHits.map((hit) => ({
      ...hit,
      document_title: corpus[hit.index].document_title,
      article_start: corpus[hit.index].article_start,
      article_end: corpus[hit.index].article_end,
    })),
    evidence,
  };
}

function printReadable(result) {
  console.log(`# ${result.query}`);
  console.log(`\n策略: ${result.strategy}`);
  result.evidence.forEach((row, index) => {
    const location = [row.chapter_title, row.section_title, row.article_start, row.article_end].filter(Boolean).join(" / ");
    const retrieval = row.retrieval
      ? `RRF=${row.retrieval.rrf.toFixed(6)} BM25#${row.retrieval.bm25_rank ?? "-"} Vector#${row.retrieval.vector_rank ?? "-"}`
      : row.retrieval_role;
    console.log(`\n${index + 1}. ${row.document_title}${location ? ` | ${location}` : ""}`);
    console.log(`   ${retrieval}`);
    console.log(`   ${row.text.replace(/\s+/g, " ").slice(0, 260)}`);
    console.log(`   本地: ${row.local_file_path}`);
    if (row.official_url) console.log(`   官网: ${row.official_url}`);
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const options = parseArgs(process.argv.slice(2));
  if (!options.query) {
    console.error("用法: node scripts/hybrid_search.mjs <问题> [--limit 10] [--json]");
    process.exit(2);
  }
  hybridSearch(options.query, { evidenceLimit: options.evidenceLimit })
    .then((result) => options.json ? console.log(JSON.stringify(result, null, 2)) : printReadable(result))
    .catch((error) => {
      console.error(error.stack || error.message);
      process.exitCode = 1;
    });
}
