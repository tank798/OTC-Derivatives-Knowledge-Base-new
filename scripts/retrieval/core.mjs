import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

export const ROOT = resolve(import.meta.dirname, "../..");
export const SOURCE_CHUNKS = resolve(ROOT, "data/processed/chunks/jsonl/all_chunks.jsonl");
export const INDEX_DIR = resolve(ROOT, "data/index");
export const CORPUS_PATH = resolve(INDEX_DIR, "corpus.jsonl");
export const METADATA_PATH = resolve(INDEX_DIR, "document_metadata.jsonl");
export const MANIFEST_PATH = resolve(INDEX_DIR, "manifest.json");
export const BM25_PATH = resolve(INDEX_DIR, "bm25/index.json");
export const VECTOR_PATH = resolve(INDEX_DIR, "vectors.f32");
export const VECTOR_METADATA_PATH = resolve(INDEX_DIR, "vector_metadata.json");
export const MODEL_ID = "Xenova/bge-base-zh-v1.5";
export const MODEL_REVISION = "71e50dc531959f9e04ebf190ea25b00261a0a186";
export const MODEL_DTYPE = "q8";
export const MODEL_DIMENSION = 768;
export const MODEL_CACHE = resolve(ROOT, ".cache/huggingface");
export const QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章：";

export const DOMAIN_TERMS = [
  "场外衍生品", "场外期权", "非标准化期权", "收益互换", "总收益互换", "利率互换",
  "信用衍生品", "信用保护工具", "信用风险缓释工具", "信用保护合约", "信用风险缓释凭证",
  "衍生品交易", "金融衍生品", "主协议", "补充协议", "交易确认书", "定义文件",
  "终止净额", "提前终止", "违约事件", "履约保障", "变动保证金", "初始保证金",
  "保证金", "担保品", "标准仓单", "中央对手方", "非集中清算", "交易报告库",
  "适当性管理", "专业投资者", "合格投资者", "风险承受能力", "风险揭示",
  "交易商", "一级交易商", "二级交易商", "交易对手", "净资本", "风险控制指标",
  "标的范围", "挂钩标的", "估值", "定价", "信息披露", "信息报送", "备案",
  "证券公司", "期货公司", "风险管理公司", "私募基金", "资产管理计划",
  "跨境交易", "外汇衍生品", "商品衍生品", "权益类衍生品", "期货和衍生品法",
];

export function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => line.trim())
    .map((line, index) => {
      try {
        return JSON.parse(line);
      } catch (error) {
        throw new Error(`JSONL解析失败 ${path}:${index + 1}: ${error.message}`);
      }
    });
}

export function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function sha256File(path) {
  return sha256Buffer(readFileSync(path));
}

export function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function normalizeTitle(value = "") {
  return value
    .normalize("NFKC")
    .replace(/\.(pdf|docx?|xlsx?|txt|md|html)$/i, "")
    .replace(/[\s·•・]/g, "")
    .replace(/[“”‘’"'《》<>【】\[\]]/g, "")
    .replace(/[，,。；;：:！!？?]/g, "")
    .toLowerCase();
}

export function normalizeText(value = "") {
  return value.normalize("NFKC").replace(/\s+/g, "").trim();
}

export function tokenize(value = "") {
  const text = value.normalize("NFKC").toLowerCase();
  const tokens = [];
  for (const match of text.matchAll(/[a-z0-9]+(?:[._/-][a-z0-9]+)*/g)) {
    tokens.push(match[0]);
  }
  for (const match of text.matchAll(/[\p{Script=Han}]+/gu)) {
    const run = match[0];
    if (run.length === 1) tokens.push(run);
    for (let index = 0; index < run.length - 1; index += 1) {
      tokens.push(run.slice(index, index + 2));
    }
  }
  for (const term of DOMAIN_TERMS) {
    if (text.includes(term.toLowerCase())) tokens.push(`term:${term.toLowerCase()}`);
  }
  return tokens;
}

export function chunkSearchText(row) {
  return [
    row.document_title,
    row.chapter_title,
    row.section_title,
    row.article_start,
    row.article_end,
    ...(row.section_path ?? []),
    row.document_number,
    row.issuing_authority,
    row.text,
  ].filter(Boolean).join("\n");
}

export function buildBm25(corpus, { k1 = 1.5, b = 0.75 } = {}) {
  const postings = new Map();
  const documentLengths = [];
  for (let docIndex = 0; docIndex < corpus.length; docIndex += 1) {
    const terms = tokenize(chunkSearchText(corpus[docIndex]));
    documentLengths.push(terms.length);
    const frequencies = new Map();
    for (const term of terms) frequencies.set(term, (frequencies.get(term) ?? 0) + 1);
    for (const [term, frequency] of frequencies) {
      const list = postings.get(term) ?? [];
      list.push([docIndex, frequency]);
      postings.set(term, list);
    }
  }
  const sortedPostings = Object.fromEntries([...postings.entries()].sort(([a], [b]) => a.localeCompare(b)));
  const averageDocumentLength = documentLengths.reduce((sum, value) => sum + value, 0) / Math.max(1, corpus.length);
  return {
    version: 1,
    tokenizer: "nfkc+cjk_bigram+otc_domain_terms",
    fieldWeighting: "none",
    k1,
    b,
    documentCount: corpus.length,
    averageDocumentLength,
    documentLengths,
    postings: sortedPostings,
  };
}

export function searchBm25(query, corpus, index, limit = 30) {
  const queryTerms = [...new Set(tokenize(query))];
  const scores = new Float64Array(corpus.length);
  const { k1, b, documentCount: n, averageDocumentLength: avgdl, documentLengths } = index;
  for (const term of queryTerms) {
    const postingList = index.postings[term];
    if (!postingList?.length) continue;
    const df = postingList.length;
    const idf = Math.log((n - df + 0.5) / (df + 0.5) + 1);
    for (const [docIndex, frequency] of postingList) {
      const lengthNormalization = k1 * (1 - b + b * (documentLengths[docIndex] / Math.max(avgdl, 1)));
      scores[docIndex] += idf * ((frequency * (k1 + 1)) / (frequency + lengthNormalization));
    }
  }
  return topScores(scores, corpus, limit, "bm25");
}

export function topScores(scores, corpus, limit, scoreField) {
  const hits = [];
  for (let index = 0; index < scores.length; index += 1) {
    const score = scores[index];
    if (score > 0) hits.push({ index, chunk_id: corpus[index].chunk_id, [scoreField]: score });
  }
  hits.sort((a, b) => b[scoreField] - a[scoreField] || a.index - b.index);
  return hits.slice(0, limit).map((hit, rank) => ({ ...hit, rank: rank + 1 }));
}

export function loadVectorMatrix(path, count, dimension) {
  const buffer = readFileSync(path);
  const expectedBytes = count * dimension * Float32Array.BYTES_PER_ELEMENT;
  if (buffer.byteLength !== expectedBytes) {
    throw new Error(`向量文件大小不匹配: expected=${expectedBytes}, actual=${buffer.byteLength}`);
  }
  return new Float32Array(buffer.buffer, buffer.byteOffset, count * dimension);
}

export function searchVectors(queryVector, matrix, corpus, dimension, limit = 30) {
  if (queryVector.length !== dimension) throw new Error("查询向量维度不匹配");
  const scores = new Float64Array(corpus.length);
  for (let row = 0; row < corpus.length; row += 1) {
    let dot = 0;
    const offset = row * dimension;
    for (let column = 0; column < dimension; column += 1) dot += matrix[offset + column] * queryVector[column];
    scores[row] = dot;
  }
  return topScores(scores, corpus, limit, "vector");
}

export function reciprocalRankFusion(bm25Hits, vectorHits, { k = 60, limit = 20 } = {}) {
  const fused = new Map();
  const add = (hit, source) => {
    const current = fused.get(hit.chunk_id) ?? {
      chunk_id: hit.chunk_id,
      index: hit.index,
      rrf: 0,
      bm25_rank: null,
      vector_rank: null,
      bm25_score: null,
      vector_score: null,
    };
    current.rrf += 1 / (k + hit.rank);
    current[`${source}_rank`] = hit.rank;
    current[`${source}_score`] = hit[source];
    fused.set(hit.chunk_id, current);
  };
  bm25Hits.forEach((hit) => add(hit, "bm25"));
  vectorHits.forEach((hit) => add(hit, "vector"));
  return [...fused.values()]
    .sort((a, b) => b.rrf - a.rrf || (a.bm25_rank ?? Infinity) - (b.bm25_rank ?? Infinity) || a.index - b.index)
    .slice(0, limit)
    .map((hit, rank) => ({ ...hit, rank: rank + 1 }));
}

export function diversifyByDocument(
  hits,
  corpus,
  {
    maxPerDocument = 3,
    limit = 10,
  } = {},
) {
  if (!Number.isInteger(maxPerDocument) || maxPerDocument < 1) {
    throw new Error("maxPerDocument 必须是正整数");
  }
  if (!Number.isInteger(limit) || limit < 1) throw new Error("limit 必须是正整数");
  const selected = [];
  const counts = new Map();
  const documentIdOf = (hit) => corpus[hit.index]?.document_id || `unknown:${hit.chunk_id}`;

  // 同一份法规最多进入3个Chunk，避免单一长文占满10条上下文。
  // 这是与法规名称、题目无关的通用约束；仍按原始RRF顺序保留每份法规最强的Chunk。
  for (const hit of hits) {
    if (selected.length >= limit) break;
    const documentId = documentIdOf(hit);
    const count = counts.get(documentId) ?? 0;
    if (count >= maxPerDocument) continue;
    counts.set(documentId, count + 1);
    selected.push(hit);
  }

  return selected.map((hit, rank) => ({ ...hit, rank: rank + 1 }));
}

function containmentSimilarity(left, right) {
  const a = normalizeText(left);
  const b = normalizeText(right);
  if (!a || !b) return 0;
  if (a.includes(b) || b.includes(a)) return Math.min(a.length, b.length) / Math.max(a.length, b.length);
  return 0;
}

export function assembleEvidence(fusedHits, corpus, { limit = 10, maxWithContext = 14 } = {}) {
  const byChunkId = new Map(corpus.map((row, index) => [row.chunk_id, { row, index }]));
  const byDocument = new Map();
  corpus.forEach((row, index) => {
    const list = byDocument.get(row.document_id) ?? [];
    list.push({ row, index });
    byDocument.set(row.document_id, list);
  });
  for (const list of byDocument.values()) list.sort((a, b) => a.row.chunk_index - b.row.chunk_index);

  const selected = [];
  const selectedIds = new Set();
  const textHashes = new Set();
  const add = (row, retrieval, role) => {
    if (!row || selectedIds.has(row.chunk_id) || selected.length >= maxWithContext) return false;
    const textHash = sha256Buffer(normalizeText(row.text));
    if (textHashes.has(textHash)) return false;
    if (row.overlap_source_chunk_id && selectedIds.has(row.overlap_source_chunk_id)) {
      const source = byChunkId.get(row.overlap_source_chunk_id)?.row;
      if (source && containmentSimilarity(source.text, row.text) >= 0.85) return false;
    }
    selectedIds.add(row.chunk_id);
    textHashes.add(textHash);
    selected.push({
      ...row,
      retrieval_role: role,
      retrieval: retrieval ?? null,
      citation: {
        document_title: row.document_title,
        article_start: row.article_start,
        article_end: row.article_end,
        local_file_path: row.local_file_path,
        official_url: row.official_url,
      },
    });
    return true;
  };

  const contextCandidates = [];
  for (const hit of fusedHits.slice(0, limit)) {
    const row = corpus[hit.index];
    add(row, hit, "primary");
    if (row.overlap_source_chunk_id) {
      contextCandidates.push({ row: byChunkId.get(row.overlap_source_chunk_id)?.row, role: "overlap_source" });
    }
    const openingText = row.text.slice(0, 220);
    if (/(^|\n)(前条|前款|前项|上述规定|依照前款|除前款)/.test(openingText)) {
      const siblings = byDocument.get(row.document_id) ?? [];
      const position = siblings.findIndex((item) => item.row.chunk_id === row.chunk_id);
      if (position > 0) contextCandidates.push({ row: siblings[position - 1].row, role: "dependency_context" });
    }
  }
  for (const candidate of contextCandidates) {
    if (selected.length >= maxWithContext) break;
    add(candidate.row, null, candidate.role);
  }
  return selected;
}

export function splitEmbeddingText(row, maxBodyChars = 420, overlapChars = 40) {
  const location = [row.chapter_title, row.section_title, row.article_start, row.article_end].filter(Boolean).join(" / ");
  const prefix = `法规：${row.document_title}\n位置：${location || "正文"}\n`;
  const body = row.text || "";
  if (body.length <= maxBodyChars) return [prefix + body];
  const segments = [];
  const step = maxBodyChars - overlapChars;
  for (let start = 0; start < body.length; start += step) {
    segments.push(prefix + body.slice(start, start + maxBodyChars));
    if (start + maxBodyChars >= body.length) break;
  }
  return segments;
}

export function embeddingInputFingerprint(corpus) {
  const hash = createHash("sha256");
  for (const row of corpus) {
    for (const segment of splitEmbeddingText(row)) hash.update(segment).update("\u0000");
    hash.update("\u0001");
  }
  return hash.digest("hex");
}

export function normalizeVector(vector) {
  let norm = 0;
  for (const value of vector) norm += value * value;
  norm = Math.sqrt(norm) || 1;
  const output = new Float32Array(vector.length);
  for (let index = 0; index < vector.length; index += 1) output[index] = vector[index] / norm;
  return output;
}

export function loadIndexArtifacts() {
  const corpus = readJsonl(CORPUS_PATH);
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  const bm25 = JSON.parse(readFileSync(BM25_PATH, "utf8"));
  const vectorMetadata = JSON.parse(readFileSync(VECTOR_METADATA_PATH, "utf8"));
  if (manifest.corpus.chunk_count !== corpus.length) throw new Error("manifest与corpus数量不一致");
  if (vectorMetadata.chunk_count !== corpus.length) throw new Error("vector metadata与corpus数量不一致");
  if (sha256File(CORPUS_PATH) !== manifest.corpus.sha256) throw new Error("corpus哈希与manifest不一致");
  return { corpus, manifest, bm25, vectorMetadata };
}

export function resolveProjectPath(path = "") {
  return path ? resolve(ROOT, path) : "";
}
