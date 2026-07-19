import assert from "node:assert/strict";
import { existsSync, statSync } from "node:fs";
import test from "node:test";
import {
  MANIFEST_PATH,
  MODEL_DIMENSION,
  VECTOR_PATH,
  assembleEvidence,
  diversifyByDocument,
  loadIndexArtifacts,
  loadVectorMatrix,
  reciprocalRankFusion,
  resolveProjectPath,
  searchBm25,
  tokenize,
} from "./core.mjs";

const HAS_INDEX = existsSync(MANIFEST_PATH);

test("检索语料与manifest数量一致且不含占位清单", { skip: !HAS_INDEX && "尚未基于114份正式法规重建索引" }, () => {
  const { corpus, manifest } = loadIndexArtifacts();
  assert.equal(manifest.corpus.document_count, 114);
  assert.equal(corpus.length, manifest.corpus.chunk_count);
  assert.equal(new Set(corpus.map((row) => row.chunk_id)).size, corpus.length);
  assert.equal(new Set(corpus.map((row) => row.document_id)).size, 114);
  assert.ok(corpus.every((row) => !row.file_name.includes("监管缺口文件粘贴总清单")));
  assert.ok(corpus.every((row) => existsSync(resolveProjectPath(row.local_file_path))));
  assert.equal(manifest.source.path, "data/processed/chunks/jsonl/all_chunks.jsonl");
  assert.equal(manifest.source.legacy_clauses_enabled, false);
});

test("向量文件与Chunk行号严格对应", { skip: !HAS_INDEX && "尚未基于114份正式法规重建索引" }, () => {
  const { corpus, vectorMetadata } = loadIndexArtifacts();
  assert.equal(vectorMetadata.dimension, MODEL_DIMENSION);
  assert.equal(vectorMetadata.chunk_count, corpus.length);
  assert.deepEqual(vectorMetadata.row_chunk_ids, corpus.map((row) => row.chunk_id));
  assert.equal(statSync(VECTOR_PATH).size, corpus.length * MODEL_DIMENSION * 4);
  const matrix = loadVectorMatrix(VECTOR_PATH, corpus.length, MODEL_DIMENSION);
  for (let row = 0; row < corpus.length; row += 1) {
    let squaredNorm = 0;
    for (let column = 0; column < MODEL_DIMENSION; column += 1) {
      const value = matrix[row * MODEL_DIMENSION + column];
      assert.ok(Number.isFinite(value));
      squaredNorm += value * value;
    }
    assert.ok(Math.abs(Math.sqrt(squaredNorm) - 1) < 1e-4);
  }
});

test("中文BM25包含专业词且不使用字段权重", { skip: !HAS_INDEX && "尚未基于114份正式法规重建索引" }, () => {
  const { corpus, bm25, manifest } = loadIndexArtifacts();
  assert.ok(tokenize("非集中清算衍生品交易保证金").includes("term:非集中清算"));
  assert.equal(manifest.bm25.field_weighting, "none");
  const hits = searchBm25("非集中清算衍生品交易保证金", corpus, bm25, 10);
  const titles = hits.map((hit) => corpus[hit.index].document_title);
  assert.ok(titles.some((title) => title.includes("非集中清算衍生品交易保证金")));
});

test("输入准确法规名称能够召回对应法规", { skip: !HAS_INDEX && "尚未基于114份正式法规重建索引" }, () => {
  const { corpus, bm25 } = loadIndexArtifacts();
  const title = "证券公司场外期权业务管理办法";
  const hits = searchBm25(title, corpus, bm25, 10);
  assert.ok(hits.some((hit) => corpus[hit.index].document_title === title));
});

test("输入文号能够召回对应法规", { skip: !HAS_INDEX && "尚未基于114份正式法规重建索引" }, () => {
  const { corpus, bm25 } = loadIndexArtifacts();
  const hits = searchBm25("主席令第一一一号", corpus, bm25, 10);
  assert.ok(hits.some((hit) => corpus[hit.index].document_title === "中华人民共和国期货和衍生品法"));
});

test("RRF对BM25和向量使用相同公式", () => {
  const fused = reciprocalRankFusion(
    [{ chunk_id: "a", index: 0, rank: 1, bm25: 10 }, { chunk_id: "b", index: 1, rank: 2, bm25: 9 }],
    [{ chunk_id: "b", index: 1, rank: 1, vector: 0.8 }, { chunk_id: "a", index: 0, rank: 2, vector: 0.7 }],
    { k: 60, limit: 2 },
  );
  assert.equal(fused.length, 2);
  assert.equal(fused[0].rrf, fused[1].rrf);
  assert.equal(fused[0].bm25_rank, 1);
  assert.equal(fused[0].vector_rank, 2);
});

test("同一法规最多保留3个Chunk", () => {
  const corpus = [
    { chunk_id: "a1", document_id: "a" },
    { chunk_id: "a2", document_id: "a" },
    { chunk_id: "a3", document_id: "a" },
    { chunk_id: "a4", document_id: "a" },
    { chunk_id: "b1", document_id: "b" },
    { chunk_id: "c1", document_id: "c" },
  ];
  const scores = [0.033, 0.032, 0.031, 0.030, 0.0295, 0.015];
  const hits = corpus.map((row, index) => ({ chunk_id: row.chunk_id, index, rank: index + 1, rrf: scores[index] }));
  const diversified = diversifyByDocument(hits, corpus, {
    maxPerDocument: 3,
    limit: 5,
  });

  assert.deepEqual(diversified.map((hit) => hit.chunk_id), ["a1", "a2", "a3", "b1", "c1"]);
  assert.equal(diversified.filter((hit) => corpus[hit.index].document_id === "a").length, 3);
});

test("法规级上限对强溢出Chunk同样生效", () => {
  const corpus = [
    { chunk_id: "a1", document_id: "a" },
    { chunk_id: "a2", document_id: "a" },
    { chunk_id: "a3", document_id: "a" },
    { chunk_id: "a4", document_id: "a" },
    { chunk_id: "b1", document_id: "b" },
  ];
  const scores = [0.033, 0.032, 0.031, 0.030, 0.020];
  const hits = corpus.map((row, index) => ({ chunk_id: row.chunk_id, index, rank: index + 1, rrf: scores[index] }));
  const diversified = diversifyByDocument(hits, corpus, {
    maxPerDocument: 3,
    limit: 4,
  });

  assert.deepEqual(diversified.map((hit) => hit.chunk_id), ["a1", "a2", "a3", "b1"]);
});

test("证据整理去除完全重复正文", () => {
  const corpus = [
    { chunk_id: "a", document_id: "d", chunk_index: 1, text: "相同正文", document_title: "甲", local_file_path: "a", official_url: "" },
    { chunk_id: "b", document_id: "d", chunk_index: 2, text: "相同 正文", document_title: "甲", local_file_path: "a", official_url: "" },
  ];
  const evidence = assembleEvidence([
    { chunk_id: "a", index: 0, rank: 1, rrf: 1 },
    { chunk_id: "b", index: 1, rank: 2, rrf: 0.5 },
  ], corpus, { limit: 2 });
  assert.equal(evidence.length, 1);
});

test("前置上下文不会挤出Top K主检索结果", () => {
  const corpus = [
    { chunk_id: "context", document_id: "d1", chunk_index: 1, text: "第一条 上下文", document_title: "甲", local_file_path: "a", official_url: "" },
    { chunk_id: "primary-a", document_id: "d1", chunk_index: 2, text: "前款规定继续适用", document_title: "甲", local_file_path: "a", official_url: "" },
    { chunk_id: "primary-b", document_id: "d2", chunk_index: 1, text: "独立主结果", document_title: "乙", local_file_path: "b", official_url: "" },
  ];
  const evidence = assembleEvidence([
    { chunk_id: "primary-a", index: 1, rank: 1, rrf: 1 },
    { chunk_id: "primary-b", index: 2, rank: 2, rrf: 0.5 },
  ], corpus, { limit: 2, maxWithContext: 2 });
  assert.deepEqual(evidence.map((row) => row.chunk_id), ["primary-a", "primary-b"]);
});
