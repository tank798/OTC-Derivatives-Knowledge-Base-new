#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  BM25_PATH,
  CORPUS_PATH,
  MANIFEST_PATH,
  METADATA_PATH,
  MODEL_DIMENSION,
  ROOT,
  SOURCE_CHUNKS,
  VECTOR_METADATA_PATH,
  VECTOR_PATH,
  buildBm25,
  embeddingInputFingerprint,
  readJsonl,
  sha256File,
} from "./retrieval/core.mjs";

const target = process.argv.slice(2).join(" ").trim();
if (!target) throw new Error("用法: node scripts/remove_document_from_kb.mjs <文件名或法规名称>");

const writeJsonl = (path, rows) => writeFileSync(path, rows.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf8");
const matches = (row) => row.file_name === target || row.document_title === target || row.file_name?.includes(target) || row.document_title?.includes(target);

const oldCorpus = readJsonl(CORPUS_PATH);
const removedIndexes = new Set(oldCorpus.map((row, index) => matches(row) ? index : -1).filter((index) => index >= 0));
if (!removedIndexes.size) throw new Error(`未找到目标文件: ${target}`);

const corpus = oldCorpus.filter((_, index) => !removedIndexes.has(index)).map((row, row_index) => ({ ...row, row_index }));
const chunks = readJsonl(SOURCE_CHUNKS).filter((row) => !matches(row));
const metadata = readJsonl(METADATA_PATH).filter((row) => !matches(row));
writeJsonl(CORPUS_PATH, corpus);
writeJsonl(SOURCE_CHUNKS, chunks);
writeJsonl(METADATA_PATH, metadata);
writeJsonl(resolve(ROOT, "data/metadata/regulations.jsonl"), metadata);
writeFileSync(BM25_PATH, JSON.stringify(buildBm25(corpus)), "utf8");

const oldBuffer = readFileSync(VECTOR_PATH);
const oldVectors = new Float32Array(oldBuffer.buffer, oldBuffer.byteOffset, oldCorpus.length * MODEL_DIMENSION);
const vectors = new Float32Array(corpus.length * MODEL_DIMENSION);
let outputRow = 0;
for (let inputRow = 0; inputRow < oldCorpus.length; inputRow += 1) {
  if (removedIndexes.has(inputRow)) continue;
  vectors.set(oldVectors.subarray(inputRow * MODEL_DIMENSION, (inputRow + 1) * MODEL_DIMENSION), outputRow * MODEL_DIMENSION);
  outputRow += 1;
}
writeFileSync(VECTOR_PATH, Buffer.from(vectors.buffer));

const vectorMetadata = JSON.parse(readFileSync(VECTOR_METADATA_PATH, "utf8"));
vectorMetadata.chunk_count = corpus.length;
vectorMetadata.row_chunk_ids = corpus.map((row) => row.chunk_id);
vectorMetadata.embedding_input_sha256 = embeddingInputFingerprint(corpus);
vectorMetadata.vectors_sha256 = sha256File(VECTOR_PATH);
vectorMetadata.corpus_sha256 = sha256File(CORPUS_PATH);
writeFileSync(VECTOR_METADATA_PATH, JSON.stringify(vectorMetadata, null, 2) + "\n", "utf8");

const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
manifest.generated_at = new Date().toISOString();
manifest.source.sha256 = sha256File(SOURCE_CHUNKS);
manifest.corpus.sha256 = sha256File(CORPUS_PATH);
manifest.corpus.document_count = metadata.length;
manifest.corpus.chunk_count = corpus.length;
manifest.corpus.official_url_count = metadata.filter((row) => row.official_url).length;
manifest.bm25.sha256 = sha256File(BM25_PATH);
manifest.vectors.sha256 = sha256File(VECTOR_PATH);
manifest.vectors.chunk_count = corpus.length;
manifest.removals = [...(manifest.removals ?? []), { target, reason: "非监管文件/占位清单", removed_chunks: removedIndexes.size }];
writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n", "utf8");

console.log(JSON.stringify({ target, removedChunks: removedIndexes.size, documents: metadata.length, chunks: corpus.length }));
