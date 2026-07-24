#!/usr/bin/env node

import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import {
  INDEX_DIR as DEFAULT_INDEX_DIR,
  MODEL_CACHE,
  MODEL_DIMENSION,
  MODEL_DTYPE,
  MODEL_ID,
  MODEL_REVISION,
  ROOT,
  SOURCE_CHUNKS as DEFAULT_SOURCE_CHUNKS,
  buildBm25,
  embeddingInputFingerprint,
  normalizeText,
  normalizeTitle,
  normalizeVector,
  readJsonl,
  loadVectorMatrix,
  sha256Buffer,
  sha256File,
  splitEmbeddingText,
  stableJson,
  validateExistingVectorCompatibility,
} from "./retrieval/core.mjs";

const WITH_VECTORS = process.argv.includes("--with-vectors");
const INCREMENTAL_VECTORS = process.argv.includes("--incremental-vectors");
function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? resolve(process.argv[index + 1]) : fallback;
}
const SOURCE_CHUNKS_PATH = argValue("--source-chunks", DEFAULT_SOURCE_CHUNKS);
const INDEX_DIR = argValue("--output-dir", DEFAULT_INDEX_DIR);
const REUSE_INDEX_DIR = argValue("--reuse-index", DEFAULT_INDEX_DIR);
const CORPUS_PATH = resolve(INDEX_DIR, "corpus.jsonl");
const METADATA_PATH = resolve(INDEX_DIR, "document_metadata.jsonl");
const MANIFEST_PATH = resolve(INDEX_DIR, "manifest.json");
const BM25_PATH = resolve(INDEX_DIR, "bm25/index.json");
const VECTOR_PATH = resolve(INDEX_DIR, "vectors.f32");
const VECTOR_METADATA_PATH = resolve(INDEX_DIR, "vector_metadata.json");
const CATALOG_PATH = resolve(ROOT, "data/metadata/authoritative_regulatory_catalog.json");
const CANONICAL_PATH = resolve(ROOT, "data/metadata/regulations.jsonl");
const DUPLICATE_AUDIT_PATH = resolve(INDEX_DIR, "duplicate_audit.csv");
const VECTOR_REUSE_AUDIT_PATH = resolve(INDEX_DIR, "incremental_vector_audit.csv");

function metadataKeys(row) {
  const values = [
    row.document_title,
    row.file_name,
    row.canonical_title,
    row.title,
    row.normalized_filename,
    ...(row.aliases ?? []),
    ...(row.original_filenames ?? []),
  ];
  return [...new Set(values.filter(Boolean).map(normalizeTitle).filter(Boolean))];
}

function loadMetadataLookup() {
  const lookup = new Map();
  const add = (row, priority) => {
    for (const key of metadataKeys(row)) {
      const current = lookup.get(key);
      if (!current || priority > current.priority) lookup.set(key, { row, priority });
    }
  };
  if (existsSync(CANONICAL_PATH)) {
    for (const row of readJsonl(CANONICAL_PATH)) add(row, 1);
  }
  if (existsSync(CATALOG_PATH)) {
    const catalog = JSON.parse(readFileSync(CATALOG_PATH, "utf8"));
    for (const row of catalog.entries ?? []) add(row, 2);
  }
  return lookup;
}

function mergeMetadata(chunk, external) {
  const officialUrls = external?.official_urls ?? [];
  return {
    official_url: external?.official_url || officialUrls[0] || "",
    issuing_authority: chunk.issuing_authority || external?.issuing_authority || external?.actual_publisher || external?.publisher || external?.catalog_group || "",
    document_number: chunk.document_number || external?.document_number || external?.preferred_version?.document_number || "",
    publication_date: chunk.publication_date || external?.publication_date || external?.published_at || external?.preferred_version?.published_at || "",
    effective_date: chunk.effective_date || external?.effective_date || external?.effective_at || external?.preferred_version?.effective_at || "",
    validity_status: chunk.validity_status || external?.validity_status || external?.status || external?.preferred_version?.status || "",
  };
}

function buildCorpus(chunks, lookup) {
  return chunks.map((chunk, rowIndex) => {
    const external = lookup.get(normalizeTitle(chunk.document_title))?.row
      ?? lookup.get(normalizeTitle(chunk.file_name))?.row;
    const metadata = mergeMetadata(chunk, external);
    return {
      row_index: rowIndex,
      chunk_id: chunk.chunk_id,
      document_id: chunk.document_id,
      chunk_index: chunk.chunk_index,
      document_title: chunk.document_title,
      document_title_source: chunk.document_title_source,
      chapter_title: chunk.chapter_title,
      section_title: chunk.section_title,
      part_title: chunk.part_title,
      article_start: chunk.article_start,
      article_end: chunk.article_end,
      paragraph_range: chunk.paragraph_range,
      text: chunk.text,
      character_count: chunk.character_count,
      file_name: chunk.file_name,
      local_file_path: chunk.file_path,
      source_type: chunk.source_type,
      official_url: metadata.official_url,
      issuing_authority: metadata.issuing_authority,
      document_number: metadata.document_number,
      publication_date: metadata.publication_date,
      effective_date: metadata.effective_date,
      validity_status: metadata.validity_status,
      version: chunk.version,
      is_overlapping: Boolean(chunk.is_overlapping),
      overlap_source_chunk_id: chunk.overlap_source_chunk_id || "",
      source_block_ids: chunk.source_block_ids ?? [],
      block_ids: chunk.block_ids ?? chunk.source_block_ids ?? [],
      primary_block_ids: chunk.primary_block_ids ?? [],
      overlap_block_ids: chunk.overlap_block_ids ?? [],
      start_char: chunk.start_char ?? -1,
      end_char: chunk.end_char ?? -1,
      source_page_start: chunk.source_page_start ?? 0,
      source_page_end: chunk.source_page_end ?? 0,
      section_path: chunk.section_path ?? [],
      overlap_left: chunk.overlap_left ?? 0,
      overlap_right: chunk.overlap_right ?? 0,
      clean_text_hash: chunk.clean_text_hash ?? "",
      chunk_hash: chunk.chunk_hash ?? "",
    };
  });
}

function writeJsonl(path, rows) {
  writeFileSync(path, rows.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf8");
}

function buildDocumentMetadata(corpus) {
  const documents = new Map();
  for (const row of corpus) {
    const current = documents.get(row.document_id) ?? {
      document_id: row.document_id,
      document_title: row.document_title,
      file_name: row.file_name,
      local_file_path: row.local_file_path,
      source_type: row.source_type,
      official_url: row.official_url,
      issuing_authority: row.issuing_authority,
      document_number: row.document_number,
      publication_date: row.publication_date,
      effective_date: row.effective_date,
      validity_status: row.validity_status,
      version: row.version,
      chunk_count: 0,
      character_count: 0,
    };
    current.chunk_count += 1;
    current.character_count += row.character_count || row.text.length;
    documents.set(row.document_id, current);
  }
  for (const document of documents.values()) {
    const sourcePath = resolve(ROOT, document.local_file_path);
    if (!existsSync(sourcePath)) throw new Error(`本地原件不存在: ${document.local_file_path}`);
    document.file_sha256 = sha256File(sourcePath);
    document.file_size = statSync(sourcePath).size;
  }
  return [...documents.values()].sort((a, b) => a.document_title.localeCompare(b.document_title));
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function createDuplicateAudit(corpus, documents) {
  const rows = [];
  const chunkIds = new Map();
  const chunkTexts = new Map();
  const fileHashes = new Map();
  const bodyHashes = new Map();

  for (const row of corpus) {
    const ids = chunkIds.get(row.chunk_id) ?? [];
    ids.push(row);
    chunkIds.set(row.chunk_id, ids);
    const textHash = sha256Buffer(normalizeText(row.text));
    const texts = chunkTexts.get(textHash) ?? [];
    texts.push(row);
    chunkTexts.set(textHash, texts);
  }
  for (const document of documents) {
    const files = fileHashes.get(document.file_sha256) ?? [];
    files.push(document);
    fileHashes.set(document.file_sha256, files);
    const docChunks = corpus.filter((row) => row.document_id === document.document_id && !row.is_overlapping)
      .sort((a, b) => a.chunk_index - b.chunk_index);
    const normalizedTitle = normalizeText(document.document_title);
    const body = docChunks.map((row) => normalizeText(row.text).replaceAll(normalizedTitle, "")).join("");
    const bodyHash = sha256Buffer(body);
    document.normalized_body_sha256 = bodyHash;
    const bodies = bodyHashes.get(bodyHash) ?? [];
    bodies.push(document);
    bodyHashes.set(bodyHash, bodies);
  }

  const addGroups = (level, groups, statusFor) => {
    for (const [fingerprint, members] of groups) {
      if (members.length < 2) continue;
      rows.push({
        audit_level: level,
        fingerprint,
        count: members.length,
        status: statusFor(members),
        members: members.map((row) => row.chunk_id || row.file_name).join(" | "),
      });
    }
  };
  addGroups("chunk_id", chunkIds, () => "error_duplicate_id");
  addGroups("file_binary", fileHashes, () => "error_duplicate_file");
  addGroups("document_body", bodyHashes, () => "review_duplicate_body");
  addGroups("chunk_text", chunkTexts, (members) => {
    const ids = new Set(members.map((row) => row.document_id));
    return ids.size === 1 && members.some((row) => row.is_overlapping) ? "intentional_overlap" : "review_duplicate_text";
  });

  const errorRows = rows.filter((row) => row.status.startsWith("error_"));
  const reviewRows = rows.filter((row) => row.status.startsWith("review_"));
  const overlapRows = rows.filter((row) => row.status === "intentional_overlap");
  const summaries = [
    { audit_level: "summary", fingerprint: "files", count: documents.length, status: "checked", members: "" },
    { audit_level: "summary", fingerprint: "chunks", count: corpus.length, status: "checked", members: "" },
    { audit_level: "summary", fingerprint: "blocking_duplicate_groups", count: errorRows.length, status: errorRows.length ? "failed" : "passed", members: "" },
    { audit_level: "summary", fingerprint: "review_duplicate_groups", count: reviewRows.length, status: reviewRows.length ? "review" : "passed", members: "" },
    { audit_level: "summary", fingerprint: "intentional_overlap_groups", count: overlapRows.length, status: "recorded", members: "" },
  ];
  const columns = ["audit_level", "fingerprint", "count", "status", "members"];
  const csv = [columns.join(","), ...[...summaries, ...rows].map((row) => columns.map((column) => csvCell(row[column])).join(","))].join("\n") + "\n";
  writeFileSync(DUPLICATE_AUDIT_PATH, csv, "utf8");
  if (errorRows.length) throw new Error(`重复审计发现${errorRows.length}组阻断问题，详见duplicate_audit.csv`);
  return {
    blocking_duplicate_groups: errorRows.length,
    review_duplicate_groups: reviewRows.length,
    intentional_overlap_groups: overlapRows.length,
  };
}

async function buildVectors(corpus, reuseIndexDir = REUSE_INDEX_DIR) {
  const { env, pipeline } = await import("@huggingface/transformers");
  env.cacheDir = MODEL_CACHE;
  env.allowRemoteModels = false;
  mkdirSync(MODEL_CACHE, { recursive: true });
  console.log(`[Vector] 加载 ${MODEL_ID} (${MODEL_DTYPE})`);
  const extractor = await pipeline("feature-extraction", MODEL_ID, {
    dtype: MODEL_DTYPE,
    cache_dir: MODEL_CACHE,
    local_files_only: true,
  });

  const rowEmbeddingHashes = corpus.map((row) => sha256Buffer(stableJson(splitEmbeddingText(row))));
  const matrix = new Float32Array(corpus.length * MODEL_DIMENSION);
  const ownersToEmbed = [];
  let reusedCount = 0;
  let previousChunkCount = 0;
  const previousAuditByChunk = new Map();
  const reusedPreviousVectorHashes = new Map();
  const reuseCorpusPath = resolve(reuseIndexDir, "corpus.jsonl");
  const reuseVectorPath = resolve(reuseIndexDir, "vectors.f32");
  const reuseMetadataPath = resolve(reuseIndexDir, "vector_metadata.json");

  if (
    INCREMENTAL_VECTORS
    && existsSync(reuseCorpusPath)
    && existsSync(reuseVectorPath)
    && existsSync(reuseMetadataPath)
  ) {
    const previousCorpus = readJsonl(reuseCorpusPath);
    const previousMetadata = JSON.parse(readFileSync(reuseMetadataPath, "utf8"));
    if (
      previousMetadata.model_id !== MODEL_ID
      || previousMetadata.dimension !== MODEL_DIMENSION
      || previousMetadata.model_dtype !== MODEL_DTYPE
    ) {
      throw new Error("旧向量模型配置与当前配置不一致，不能增量复用");
    }
    const previousMatrix = loadVectorMatrix(
      reuseVectorPath,
      previousCorpus.length,
      MODEL_DIMENSION,
    );
    const previousRows = new Map();
    previousCorpus.forEach((row, index) => {
      const hash = sha256Buffer(stableJson(splitEmbeddingText(row)));
      previousRows.set(`${row.chunk_id}:${hash}`, index);
      const vectorHash = sha256Buffer(Buffer.from(
        previousMatrix.buffer,
        previousMatrix.byteOffset + index * MODEL_DIMENSION * Float32Array.BYTES_PER_ELEMENT,
        MODEL_DIMENSION * Float32Array.BYTES_PER_ELEMENT,
      ));
      previousAuditByChunk.set(row.chunk_id, { inputHash: hash, vectorHash });
    });
    corpus.forEach((row, owner) => {
      const previousIndex = previousRows.get(`${row.chunk_id}:${rowEmbeddingHashes[owner]}`);
      if (previousIndex === undefined) {
        ownersToEmbed.push(owner);
        return;
      }
      matrix.set(
        previousMatrix.subarray(
          previousIndex * MODEL_DIMENSION,
          (previousIndex + 1) * MODEL_DIMENSION,
        ),
        owner * MODEL_DIMENSION,
      );
      reusedPreviousVectorHashes.set(row.chunk_id, previousAuditByChunk.get(row.chunk_id)?.vectorHash ?? "");
      reusedCount += 1;
    });
    previousChunkCount = previousCorpus.length;
    console.log(`[Vector] 复用 ${reusedCount} 个未变化 Chunk，新增或变化 ${ownersToEmbed.length} 个`);
  } else {
    for (let owner = 0; owner < corpus.length; owner += 1) ownersToEmbed.push(owner);
  }

  const segments = [];
  for (const owner of ownersToEmbed) {
    for (const text of splitEmbeddingText(corpus[owner])) segments.push({ owner, text });
  }
  const sums = Array.from({ length: corpus.length }, () => new Float32Array(MODEL_DIMENSION));
  const counts = new Uint16Array(corpus.length);
  const batchSize = 48;
  for (let start = 0; start < segments.length; start += batchSize) {
    const batch = segments.slice(start, start + batchSize);
    const output = await extractor(batch.map((item) => item.text), { pooling: "cls", normalize: true });
    if (output.dims.length !== 2 || output.dims[1] !== MODEL_DIMENSION) {
      throw new Error(`Embedding维度异常: ${JSON.stringify(output.dims)}`);
    }
    for (let row = 0; row < batch.length; row += 1) {
      const owner = batch[row].owner;
      const offset = row * MODEL_DIMENSION;
      for (let column = 0; column < MODEL_DIMENSION; column += 1) sums[owner][column] += output.data[offset + column];
      counts[owner] += 1;
    }
    if (start === 0 || (start / batchSize) % 10 === 0 || start + batchSize >= segments.length) {
      console.log(`[Vector] ${Math.min(start + batchSize, segments.length)}/${segments.length} segments`);
    }
  }

  for (const row of ownersToEmbed) {
    const average = new Float32Array(MODEL_DIMENSION);
    for (let column = 0; column < MODEL_DIMENSION; column += 1) average[column] = sums[row][column] / Math.max(1, counts[row]);
    matrix.set(normalizeVector(average), row * MODEL_DIMENSION);
  }
  writeFileSync(VECTOR_PATH, Buffer.from(matrix.buffer));
  const rowVectorHashes = corpus.map((row, index) => sha256Buffer(Buffer.from(
    matrix.buffer,
    matrix.byteOffset + index * MODEL_DIMENSION * Float32Array.BYTES_PER_ELEMENT,
    MODEL_DIMENSION * Float32Array.BYTES_PER_ELEMENT,
  )));
  const auditColumns = [
    "row_index", "document_id", "chunk_id", "status",
    "previous_embedding_input_sha256", "embedding_input_sha256",
    "previous_vector_sha256", "vector_sha256", "vector_bytes_identical",
  ];
  const auditRows = corpus.map((row, index) => {
    const previous = previousAuditByChunk.get(row.chunk_id);
    const reused = reusedPreviousVectorHashes.has(row.chunk_id);
    return {
      row_index: index,
      document_id: row.document_id,
      chunk_id: row.chunk_id,
      status: reused ? "reused" : (previous ? "changed_reembedded" : "new_embedded"),
      previous_embedding_input_sha256: previous?.inputHash ?? "",
      embedding_input_sha256: rowEmbeddingHashes[index],
      previous_vector_sha256: previous?.vectorHash ?? "",
      vector_sha256: rowVectorHashes[index],
      vector_bytes_identical: reused && previous?.vectorHash === rowVectorHashes[index],
    };
  });
  writeFileSync(
    VECTOR_REUSE_AUDIT_PATH,
    [
      auditColumns.join(","),
      ...auditRows.map((row) => auditColumns.map((column) => csvCell(row[column])).join(",")),
    ].join("\n") + "\n",
    "utf8",
  );
  const metadata = {
    version: 3,
    model_id: MODEL_ID,
    model_revision: MODEL_REVISION,
    model_dtype: MODEL_DTYPE,
    pooling: "cls",
    normalization: "l2",
    long_chunk_strategy: "420_chars_with_40_char_overlap_then_normalized_mean",
    dtype: "float32",
    byte_order: "little_endian",
    dimension: MODEL_DIMENSION,
    chunk_count: corpus.length,
    segment_count: corpus.reduce((sum, row) => sum + splitEmbeddingText(row).length, 0),
    embedded_segment_count: segments.length,
    incremental_build: {
      enabled: INCREMENTAL_VECTORS,
      reused_chunk_count: reusedCount,
      embedded_chunk_count: ownersToEmbed.length,
      retired_or_changed_previous_chunk_count: Math.max(0, previousChunkCount - reusedCount),
    },
    embedding_input_sha256: embeddingInputFingerprint(corpus),
    row_embedding_input_sha256: rowEmbeddingHashes,
    row_vector_sha256: rowVectorHashes,
    incremental_audit_path: "data/index/incremental_vector_audit.csv",
    corpus_sha256: sha256File(CORPUS_PATH),
    vectors_sha256: sha256File(VECTOR_PATH),
    row_chunk_ids: corpus.map((row) => row.chunk_id),
  };
  writeFileSync(VECTOR_METADATA_PATH, JSON.stringify(metadata, null, 2) + "\n", "utf8");
  await extractor.dispose?.();
  return metadata;
}

async function main() {
  mkdirSync(INDEX_DIR, { recursive: true });
  mkdirSync(dirname(BM25_PATH), { recursive: true });
  mkdirSync(resolve(INDEX_DIR, "eval"), { recursive: true });
  const sourceChunks = readJsonl(SOURCE_CHUNKS_PATH);
  if (!sourceChunks.length) throw new Error("all_chunks.jsonl为空");
  const uniqueIds = new Set(sourceChunks.map((row) => row.chunk_id));
  if (uniqueIds.size !== sourceChunks.length) throw new Error("all_chunks.jsonl存在重复chunk_id");

  const lookup = loadMetadataLookup();
  const corpus = buildCorpus(sourceChunks, lookup);
  // Fail before writing any corpus/BM25 artifacts when an existing vector
  // matrix is incompatible. This keeps the prior index atomically usable.
  let existingVectorMetadata = null;
  if (!WITH_VECTORS && existsSync(VECTOR_METADATA_PATH) && existsSync(VECTOR_PATH)) {
    existingVectorMetadata = JSON.parse(readFileSync(VECTOR_METADATA_PATH, "utf8"));
    validateExistingVectorCompatibility(corpus, existingVectorMetadata);
  }
  // When incremental vectors reuse the same index directory, preserve the
  // previous corpus/vector pair before writing the new corpus.  Otherwise a
  // changed Chunk count makes the old vector file look corrupt (new row count,
  // old byte length) and prevents safe reuse.
  let temporaryReuseDir = "";
  let reuseIndexDir = REUSE_INDEX_DIR;
  if (INCREMENTAL_VECTORS && resolve(REUSE_INDEX_DIR) === resolve(INDEX_DIR)
    && existsSync(resolve(INDEX_DIR, "corpus.jsonl"))
    && existsSync(resolve(INDEX_DIR, "vectors.f32"))
    && existsSync(resolve(INDEX_DIR, "vector_metadata.json"))) {
    temporaryReuseDir = mkdtempSync(join(tmpdir(), "otc-retrieval-reuse-"));
    for (const file of ["corpus.jsonl", "vectors.f32", "vector_metadata.json"]) {
      copyFileSync(resolve(INDEX_DIR, file), join(temporaryReuseDir, file));
    }
    reuseIndexDir = temporaryReuseDir;
  }
  try {
    writeJsonl(CORPUS_PATH, corpus);
    const documents = buildDocumentMetadata(corpus);
    writeJsonl(METADATA_PATH, documents);
    const duplicateAudit = createDuplicateAudit(corpus, documents);

    const bm25 = buildBm25(corpus);
    writeFileSync(BM25_PATH, JSON.stringify(bm25), "utf8");
    let vectorMetadata = null;
    if (WITH_VECTORS) vectorMetadata = await buildVectors(corpus, reuseIndexDir);
    else if (existingVectorMetadata) {
      vectorMetadata = existingVectorMetadata;
      const currentEmbeddingInput = validateExistingVectorCompatibility(corpus, vectorMetadata);
      vectorMetadata.embedding_input_sha256 = currentEmbeddingInput;
      vectorMetadata.model_revision = MODEL_REVISION;
      vectorMetadata.corpus_sha256 = sha256File(CORPUS_PATH);
      vectorMetadata.vectors_sha256 = sha256File(VECTOR_PATH);
      writeFileSync(VECTOR_METADATA_PATH, JSON.stringify(vectorMetadata, null, 2) + "\n", "utf8");
    }

    const manifest = {
      version: 1,
      generated_at: new Date().toISOString(),
      source: {
        path: "data/processed/chunks/jsonl/all_chunks.jsonl",
        sha256: sha256File(SOURCE_CHUNKS_PATH),
        unique_body_source: true,
        legacy_clauses_enabled: false,
      },
      corpus: {
        path: "data/index/corpus.jsonl",
        sha256: sha256File(CORPUS_PATH),
        document_count: documents.length,
        chunk_count: corpus.length,
        official_url_count: documents.filter((row) => row.official_url).length,
      },
      bm25: {
        path: "data/index/bm25/index.json",
        sha256: sha256File(BM25_PATH),
        tokenizer: bm25.tokenizer,
        field_weighting: "none",
        k1: bm25.k1,
        b: bm25.b,
        vocabulary_size: Object.keys(bm25.postings).length,
      },
      vectors: vectorMetadata ? {
        path: "data/index/vectors.f32",
        metadata_path: "data/index/vector_metadata.json",
        sha256: vectorMetadata.vectors_sha256,
        model_id: vectorMetadata.model_id,
        model_revision: vectorMetadata.model_revision,
        model_dtype: vectorMetadata.model_dtype,
        dimension: vectorMetadata.dimension,
        chunk_count: vectorMetadata.chunk_count,
        incremental_build: vectorMetadata.incremental_build ?? null,
      } : null,
      fusion: { method: "equal_weight_rrf", rrf_k: 60, bm25_top_k: 30, vector_top_k: 30, fused_top_k: 20 },
      duplicate_audit: duplicateAudit,
      build_fingerprint: sha256Buffer(stableJson({
        source: sha256File(SOURCE_CHUNKS_PATH),
        corpus: sha256File(CORPUS_PATH),
        bm25: sha256File(BM25_PATH),
        vectors: vectorMetadata?.vectors_sha256 ?? "",
      })),
    };
    writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n", "utf8");
    const evalReadme = resolve(INDEX_DIR, "eval/README.md");
    if (!existsSync(evalReadme)) {
      writeFileSync(evalReadme, "# 手动问答核验\n\n启动本地 API 和前端，在聊天页面使用 `queries.jsonl` 中的示例问题进行真实对话测试。\n", "utf8");
    }
    console.log(JSON.stringify({
      documents: documents.length,
      chunks: corpus.length,
      official_urls: manifest.corpus.official_url_count,
      bm25_terms: manifest.bm25.vocabulary_size,
      vectors: Boolean(vectorMetadata),
      duplicate_audit: duplicateAudit,
    }, null, 2));
  } finally {
    if (temporaryReuseDir) rmSync(temporaryReuseDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
