#!/usr/bin/env python3
"""Build the standalone, public-safe Chunk viewer from the canonical corpus."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT / "data/processed/chunks/jsonl/all_chunks.jsonl"
OUTPUT_PATH = ROOT / "data/processed/chunk_review_viewer/chunk_review.html"

HISTORICAL_AUTHORITY_MAP = {
    "中国银行业监督管理委员会": "国家金融监督管理总局",
    "中国银行业监督管理委员会办公厅": "国家金融监督管理总局",
    "中国保险监督管理委员会": "国家金融监督管理总局",
    "中国保险监督管理委员会办公厅": "国家金融监督管理总局",
    "中国银行保险监督管理委员会": "国家金融监督管理总局",
    "中国银行保险监督管理委员会办公厅": "国家金融监督管理总局",
    "中国银监会": "国家金融监督管理总局",
    "中国银监会办公厅": "国家金融监督管理总局",
    "中国保监会": "国家金融监督管理总局",
    "中国保监会办公厅": "国家金融监督管理总局",
    "中国银保监会": "国家金融监督管理总局",
    "中国银保监会办公厅": "国家金融监督管理总局",
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def first_issuing_authority(value: str) -> str:
    """Return the first top-level authority without splitting punctuation in brackets."""
    text = (value or "").strip()
    if not text:
        return "其他监管机构"
    depth = 0
    for index, char in enumerate(text):
        if char in "（(【[":
            depth += 1
        elif char in "）)】]" and depth:
            depth -= 1
        elif depth == 0 and char in "、，,；;/":
            return text[:index].strip() or "其他监管机构"
    return text


def navigation_authority(value: str) -> str:
    """Build the sidebar authority while preserving the original metadata separately."""
    first = first_issuing_authority(value)
    clean = re.sub(r"[（(]经.+[）)]$", "", first).strip()
    clean = clean.removesuffix("（历史机构）").removesuffix("(历史机构)").strip()
    return HISTORICAL_AUTHORITY_MAP.get(clean, clean or "其他监管机构")


def validity_category(value: str) -> str:
    """Reduce descriptive validity text to a stable filter category."""
    text = (value or "").strip()
    if text.startswith("现行使用"):
        return "现行使用（官网仍列示）"
    if "已公布" in text and "尚未施行" in text:
        return "已公布、尚未施行"
    if text.startswith("现行有效"):
        return "现行有效"
    return text or "状态未载"


def public_data() -> dict:
    chunks = read_jsonl(CHUNKS_PATH)
    documents: OrderedDict[str, dict] = OrderedDict()
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("all_chunks.jsonl contains duplicate chunk_id values")
    for chunk in chunks:
        document_id = chunk["document_id"]
        document = documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "document_title": chunk.get("document_title", ""),
                "file_name": chunk.get("file_name", ""),
                "issuing_authority": chunk.get("issuing_authority", ""),
                "navigation_authority": navigation_authority(chunk.get("issuing_authority", "")),
                "document_number": chunk.get("document_number", ""),
                "validity_status": chunk.get("validity_status", ""),
                "validity_category": validity_category(chunk.get("validity_status", "")),
                "source_type": (
                    Path(chunk.get("file_name", "")).suffix.lstrip(".")
                    or (chunk.get("source_type", "") or "").split("+", 1)[0]
                ).upper(),
                "official_url": chunk.get("official_url", ""),
                "publication_date": chunk.get("publication_date", ""),
                "effective_date": chunk.get("effective_date", ""),
                "chunks": [],
            },
        )
        document["chunks"].append(
            {
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "body_text": chunk.get("body_text", ""),
                "article_start": chunk.get("article_start", ""),
                "article_end": chunk.get("article_end", ""),
                "chapter_title": chunk.get("chapter_title", ""),
                "section_title": chunk.get("section_title", ""),
                "part_title": chunk.get("part_title", ""),
                "attachment_name": chunk.get("attachment_name", ""),
            }
        )

    for document in documents.values():
        document["chunks"].sort(key=lambda item: item["chunk_index"])
        document["chunk_count"] = len(document["chunks"])

    authorities = {document["navigation_authority"] for document in documents.values()}
    return {
        "summary": {
            "documents": len(documents),
            "authorities": len(authorities),
            "chunks": len(chunks),
        },
        "documents": list(documents.values()),
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="中国场外衍生品法规知识库 Chunk 切分查看器">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%2310233f'/%3E%3Cpath d='M18 44h28M32 13v31M20 20h24M20 20l-8 15h16L20 20zm24 0-8 15h16L44 20z' fill='none' stroke='%23d6aa5a' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<title>中国场外衍生品法规知识库 · Chunk 切分查看</title>
<style>
:root{
  --ink:#152238;--ink-soft:#536074;--paper:#fffdf8;--canvas:#f3f0e9;
  --navy:#10233f;--navy-2:#1a3558;--line:#dcd6ca;--line-soft:#ebe6dc;
  --sidebar-bg:#faf9f6;--seal:#a4372a;--seal-soft:#f8ebe7;
  --jade:#2d6a58;--jade-soft:#e7f1ed;--shadow:0 14px 40px rgba(22,32,47,.08);
  --ui:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --reading:"STSong","Songti SC","Noto Serif CJK SC","Source Han Serif SC",serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scrollbar-width:none}
html::-webkit-scrollbar,.doc-list::-webkit-scrollbar{display:none}
body{margin:0;background:var(--canvas);color:var(--ink);font-family:var(--ui);min-height:100vh}
button,input,select{font:inherit}button,a{outline-offset:3px;touch-action:manipulation}:focus-visible{outline:2px solid var(--seal)}[hidden]{display:none!important}
.skip-link{position:fixed;left:16px;top:10px;z-index:100;padding:9px 12px;background:var(--navy);color:#fff;border-radius:8px;transform:translateY(-150%);transition:transform .16s}.skip-link:focus{transform:none}
.shell{display:grid;grid-template-columns:350px minmax(0,1fr);min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;background:var(--sidebar-bg);border-right:1px solid var(--line);display:flex;flex-direction:column;overflow:hidden}
.brand{padding:24px 20px 16px;border-bottom:1px solid var(--line)}.brand h1{font-family:var(--reading);font-size:21px;line-height:1.38;font-weight:700;color:var(--navy-2);margin:0;letter-spacing:.015em}
.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:16px 14px 14px}.summary div{min-width:0;padding:10px 8px;background:#fff;border:1px solid var(--line);border-radius:9px;text-align:center}.summary b{display:block;color:var(--navy-2);font-size:17px;line-height:1.2;font-variant-numeric:tabular-nums}.summary span{display:block;margin-top:4px;font-size:9px;color:#6b7280;white-space:nowrap}
.doc-list{overflow:auto;flex:1;padding:10px 10px 20px;border-top:1px solid var(--line-soft);scrollbar-width:none}.authority-group+.authority-group{margin-top:5px}
.authority-button{display:flex;align-items:center;width:100%;gap:8px;border:0;background:transparent;color:var(--navy-2);padding:9px;border-radius:8px;cursor:pointer;text-align:left}.authority-button:hover,.authority-button.active{background:#f0eee8}.authority-button.active{color:var(--seal)}
.authority-arrow{width:12px;color:#7b8490;font-size:10px;transition:transform .16s;flex:0 0 auto}.authority-group.open .authority-arrow{transform:rotate(90deg)}.authority-name{font-size:12px;line-height:1.45;font-weight:700;flex:1;min-width:0}.authority-count{font-size:9px;line-height:1.35;color:#7b8490;white-space:nowrap;text-align:right}
.authority-docs{padding-left:12px}.doc-button{display:flex;width:100%;align-items:flex-start;gap:8px;text-align:left;border:0;border-left:3px solid transparent;background:transparent;color:var(--ink);padding:9px 9px 9px 12px;cursor:pointer;border-radius:0 8px 8px 0;text-decoration:none;transition:background .16s,border-color .16s}.doc-button:hover{background:#f0eee8}.doc-button.active{background:#eef2f4;border-left-color:var(--seal)}.doc-title{font-family:var(--reading);font-size:12px;line-height:1.5;font-weight:600;flex:1;min-width:0}.doc-button.active .doc-title{font-weight:700;color:var(--navy-2)}.doc-count{font-size:9px;line-height:1.5;color:#7b8490;white-space:nowrap;padding-top:1px}
.main{min-width:0}.topbar{position:sticky;top:0;z-index:10;height:64px;background:rgba(243,240,233,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;padding:0 34px}.mobile-toggle{display:none;border:1px solid var(--line);background:var(--paper);border-radius:8px;padding:7px 10px;cursor:pointer}.breadcrumb{font-size:11px;letter-spacing:.08em;color:var(--ink-soft);white-space:nowrap}
.workspace{max-width:1180px;margin:0 auto;padding:28px 42px 80px}.filters-panel{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:17px 18px;box-shadow:0 7px 24px rgba(22,32,47,.05)}.filters{display:grid;grid-template-columns:minmax(250px,1.55fr) repeat(3,minmax(140px,.72fr));gap:10px}.field{min-width:0}.field label{display:block;font-size:10px;color:#7f7568;letter-spacing:.08em;margin:0 0 5px}.field input,.field select{width:100%;height:40px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);padding:0 11px;font-size:12px}.filter-result{margin:11px 1px 0;color:var(--ink-soft);font-size:10px;font-variant-numeric:tabular-nums}
.content{padding-top:22px}.document-hero{position:relative;background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:28px 30px 24px;box-shadow:var(--shadow);overflow:hidden}.document-hero::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--seal)}
.result-line{display:flex;align-items:center;gap:8px;color:var(--jade);font-size:11px;font-weight:700;letter-spacing:.08em;margin-bottom:12px}.result-line::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--jade);box-shadow:0 0 0 4px var(--jade-soft)}.document-hero h2{font-family:var(--reading);font-size:27px;line-height:1.38;margin:0;letter-spacing:.015em}.file-name{font-size:11px;color:var(--ink-soft);margin:8px 0 0}
.meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px 24px;margin:22px 0 0;padding-top:18px;border-top:1px solid var(--line-soft)}.meta div{min-width:0}.meta dt{font-size:10px;color:#7f7568;letter-spacing:.1em;margin-bottom:4px}.meta dd{font-size:12px;line-height:1.5;margin:0;word-break:break-word}.meta a{color:var(--seal);text-decoration:none;border-bottom:1px solid rgba(164,55,42,.25)}
.section-bar{display:flex;align-items:end;justify-content:space-between;gap:20px;margin:34px 2px 14px}.section-bar h3{font-family:var(--reading);font-size:20px;margin:0}.section-bar p{font-size:11px;color:var(--ink-soft);margin:0}.chunk-list{display:grid;gap:10px}
.chunk-card{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 5px 18px rgba(22,32,47,.045);animation:rise .25s ease both;scroll-margin-top:80px}.chunk-card.open{border-color:#cfc5b7}@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.chunk-head{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:13px 16px 13px 18px;background:#faf7f1;cursor:pointer;user-select:none;transition:background .16s}.chunk-head:hover{background:#f5f0e7}.chunk-card.open .chunk-head{border-bottom:1px solid var(--line-soft)}.chunk-identity{display:flex;align-items:center;gap:9px;flex-wrap:wrap;min-width:0}.chunk-number{font-family:var(--reading);font-weight:700;color:var(--seal)}.tags{display:flex;gap:5px;flex-wrap:wrap}.tag{font-size:10px;color:var(--navy-2);background:#e9eef3;border-radius:999px;padding:3px 7px}.chunk-tools{display:flex;align-items:center;gap:8px;flex-shrink:0}.chunk-actions{display:flex;gap:6px}.icon-button{border:1px solid var(--line);background:var(--paper);color:var(--ink-soft);border-radius:7px;padding:5px 8px;font-size:10px;cursor:pointer}.icon-button:hover{border-color:#b8ac9a;color:var(--seal)}.chunk-arrow{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;color:#7b8490;font-size:15px;transition:transform .16s}.chunk-card.open .chunk-arrow{transform:rotate(90deg)}
.chunk-body{font-family:var(--reading);font-size:15px;line-height:2.05;white-space:pre-wrap;word-break:break-word;padding:22px 24px 26px;color:#26354a}.hl-chapter{display:inline-block;color:var(--seal);font-size:1.08em;font-weight:700;margin-top:.3em}.hl-article{color:var(--navy-2);font-weight:700}.hl-section{color:var(--jade);font-weight:700}.hl-item{color:#8b621f;font-weight:700}.hl-attachment{color:var(--seal);font-weight:700}.match{background:#f4dc9f;color:#33250b;border-radius:2px;padding:0 1px}
.empty{padding:70px 24px;text-align:center;background:var(--paper);border:1px dashed var(--line);border-radius:14px;color:var(--ink-soft)}.doc-list .empty{padding:30px 12px;font-size:11px}.toast{position:fixed;right:24px;bottom:24px;background:var(--navy);color:#fff;padding:10px 14px;border-radius:9px;font-size:11px;opacity:0;transform:translateY(8px);pointer-events:none;transition:.2s}.toast.show{opacity:1;transform:none}
@media(max-width:1000px){.filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.shell{grid-template-columns:300px minmax(0,1fr)}.workspace{padding:24px 24px 70px}.meta{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.shell{display:block}.sidebar{position:fixed;z-index:30;left:0;top:0;width:min(88vw,350px);transform:translateX(-105%);transition:transform .22s;box-shadow:20px 0 60px rgba(0,0,0,.18);overscroll-behavior:contain}body.sidebar-open .sidebar{transform:none}.mobile-toggle{display:inline-block}.topbar{padding:0 14px;height:58px}.breadcrumb{font-size:10px}.workspace{padding:16px 14px 60px}.filters{grid-template-columns:1fr}.document-hero{padding:23px 20px}.document-hero h2{font-size:22px}.meta{grid-template-columns:1fr}.chunk-head{align-items:flex-start}.chunk-actions{display:none}.chunk-body{padding:18px;font-size:14px}.section-bar{align-items:flex-start;flex-direction:column;gap:4px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">跳到法规正文</a>
<div class="shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand"><h1>中国场外衍生品<br>法规知识库</h1></div>
    <div class="summary"><div><b id="authority-count">—</b><span>发文主体</span></div><div><b id="document-count">—</b><span>法规数量</span></div><div><b id="chunk-count">—</b><span>Chunk数量</span></div></div>
    <nav class="doc-list" id="doc-list" aria-label="发文主体与法规目录"></nav>
  </aside>
  <main class="main" id="main-content">
    <header class="topbar"><button class="mobile-toggle" id="mobile-toggle" aria-label="打开法规列表" aria-controls="sidebar" aria-expanded="false">目录</button><div class="breadcrumb">法规知识库 / Chunk 切分查看</div></header>
    <div class="workspace">
      <section class="filters-panel" aria-label="法规筛选">
        <div class="filters">
          <div class="field"><label for="query">关键词</label><input id="query" name="query" type="search" placeholder="例如：收益凭证、发文主体或文号……" autocomplete="off" spellcheck="false"></div>
          <div class="field"><label for="authority-filter">发文主体</label><select id="authority-filter" name="authority"><option value="">全部主体</option></select></div>
          <div class="field"><label for="status-filter">效力状态</label><select id="status-filter" name="status"><option value="">全部状态</option><option value="现行有效">现行有效</option><option value="现行使用（官网仍列示）">现行使用（官网仍列示）</option><option value="已公布、尚未施行">已公布、尚未施行</option></select></div>
          <div class="field"><label for="format-filter">文件格式</label><select id="format-filter" name="format"><option value="">全部格式</option></select></div>
        </div>
        <p class="filter-result" id="filter-result" role="status" aria-live="polite"></p>
      </section>
      <div class="content" id="content" aria-live="polite"></div>
    </div>
  </main>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="viewer-data">__VIEWER_DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('viewer-data').textContent);
const docs=DATA.documents;
const docMap=new Map(docs.map(doc=>[doc.document_id,doc]));
const params=new URLSearchParams(location.search);
const controls={q:document.getElementById('query'),authority:document.getElementById('authority-filter'),status:document.getElementById('status-filter'),format:document.getElementById('format-filter')};
let activeDocId=docs.length?docs[0].document_id:null;
let expandedAuthority=activeDocId?docMap.get(activeDocId).navigation_authority:null;
let openChunkId=null;

const esc=value=>String(value??'').replace(/[&<>"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
const normalize=value=>String(value??'').toLowerCase().replace(/\s+/g,'');
const articleLabel=chunk=>chunk.article_start?(chunk.article_end&&chunk.article_end!==chunk.article_start?chunk.article_start+'–'+chunk.article_end:chunk.article_start):'';
const chunkSearchText=chunk=>[chunk.body_text,articleLabel(chunk),chunk.chapter_title,chunk.section_title,chunk.part_title,chunk.attachment_name].join(' ');
const docSearchText=doc=>[doc.document_title,doc.document_number,doc.issuing_authority,doc.navigation_authority,doc.file_name].join(' ');

function highlightStructure(text,query=''){
  let html=esc(text);
  html=html.replace(/^(第[一二三四五六七八九十百千\d]+[编篇章])/gm,'<span class="hl-chapter">$1</span>');
  html=html.replace(/^(第[一二三四五六七八九十百千\d]+条)/gm,'<span class="hl-article">$1</span>');
  html=html.replace(/^(第[一二三四五六七八九十百千\d]+节)/gm,'<span class="hl-section">$1</span>');
  html=html.replace(/^([（(][一二三四五六七八九十百千\d]+[）)])/gm,'<span class="hl-item">$1</span>');
  html=html.replace(/^(附件[^\n]*)/gm,'<span class="hl-attachment">$1</span>');
  if(query){const safe=esc(query).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');html=html.replace(new RegExp('('+safe+')','gi'),'<mark class="match">$1</mark>')}
  return html;
}

function matchingChunks(doc){
  const query=normalize(controls.q.value);
  if(!query||normalize(docSearchText(doc)).includes(query))return doc.chunks;
  return doc.chunks.filter(chunk=>normalize(chunkSearchText(chunk)).includes(query));
}
function baseFiltersMatch(doc){return(!controls.authority.value||doc.navigation_authority===controls.authority.value)&&(!controls.status.value||doc.validity_category===controls.status.value)&&(!controls.format.value||doc.source_type===controls.format.value)}
function filteredDocs(){return docs.filter(doc=>baseFiltersMatch(doc)&&matchingChunks(doc).length>0)}
function syncUrl(){const url=new URL(location.href);Object.entries(controls).forEach(([key,control])=>control.value?url.searchParams.set(key,control.value):url.searchParams.delete(key));history.replaceState(null,'',url)}
function fillSelect(control,values){values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;control.appendChild(option)})}

function renderSummary(visible){
  const authorities=new Set(visible.map(doc=>doc.navigation_authority));
  const chunks=visible.reduce((sum,doc)=>sum+matchingChunks(doc).length,0);
  document.getElementById('authority-count').textContent=authorities.size;
  document.getElementById('document-count').textContent=visible.length;
  document.getElementById('chunk-count').textContent=chunks;
  document.getElementById('filter-result').textContent=`当前显示 ${authorities.size} 个发文主体、${visible.length} 份法规、${chunks} 个 Chunk`;
}

function renderDocList(visible){
  const grouped=new Map();
  visible.forEach(doc=>{const authority=doc.navigation_authority;if(!grouped.has(authority))grouped.set(authority,[]);grouped.get(authority).push(doc)});
  const active=docMap.get(activeDocId);
  const html=[...grouped].sort(([a],[b])=>a.localeCompare(b,'zh-CN')).map(([authority,groupDocs])=>{
    groupDocs.sort((a,b)=>a.document_title.localeCompare(b.document_title,'zh-CN'));
    const open=expandedAuthority===authority;
    const authorityChunks=groupDocs.reduce((sum,doc)=>sum+matchingChunks(doc).length,0);
    const docsHtml=open?`<div class="authority-docs">${groupDocs.map(doc=>`<a href="#${esc(doc.document_id)}" class="doc-button ${doc.document_id===activeDocId?'active':''}" data-doc="${esc(doc.document_id)}"><span class="doc-title">${esc(doc.document_title)}</span><span class="doc-count">${matchingChunks(doc).length} 个</span></a>`).join('')}</div>`:'';
    const selected=active&&active.navigation_authority===authority;
    return `<section class="authority-group ${open?'open':''}"><button class="authority-button ${selected?'active':''}" data-authority="${esc(authority)}" aria-expanded="${open?'true':'false'}"><span class="authority-arrow" aria-hidden="true">▶</span><span class="authority-name">${esc(authority)}</span><span class="authority-count">${groupDocs.length}部法规<br>${authorityChunks} Chunks</span></button>${docsHtml}</section>`;
  }).join('');
  document.getElementById('doc-list').innerHTML=html||'<div class="empty">没有符合当前条件的法规</div>';
}

function metaItem(label,value,html=false){return value?`<div><dt>${label}</dt><dd>${html?value:esc(value)}</dd></div>`:''}
function renderMain(visible){
  const doc=docMap.get(activeDocId);
  if(!doc||!visible.some(item=>item.document_id===activeDocId)){document.getElementById('content').innerHTML='<div class="empty">没有符合当前条件的法规或 Chunk。</div>';return}
  const chunks=matchingChunks(doc);
  if(!chunks.some(chunk=>chunk.chunk_id===openChunkId))openChunkId=chunks[0]?.chunk_id||null;
  const query=controls.q.value.trim();
  const official=doc.official_url?`<a href="${esc(doc.official_url)}" target="_blank" rel="noopener noreferrer">查看官方原文</a>`:'';
  const meta=[metaItem('文号',doc.document_number),metaItem('发文机关',doc.issuing_authority),metaItem('效力状态',doc.validity_status),metaItem('发布日期',doc.publication_date),metaItem('施行日期',doc.effective_date),metaItem('文件格式',doc.source_type),metaItem('权威来源',official,true)].join('');
  const cards=chunks.map((chunk,index)=>{
    const tags=[articleLabel(chunk),chunk.chapter_title,chunk.section_title,chunk.part_title,chunk.attachment_name].filter(Boolean);
    const open=chunk.chunk_id===openChunkId;
    const panelId='panel-'+chunk.chunk_id;
    return `<article class="chunk-card ${open?'open':''}" id="${esc(chunk.chunk_id)}" data-chunk-card="${esc(chunk.chunk_id)}" style="animation-delay:${Math.min(index*15,150)}ms"><header class="chunk-head" data-toggle-chunk="${esc(chunk.chunk_id)}" role="button" tabindex="0" aria-expanded="${open?'true':'false'}" aria-controls="${esc(panelId)}"><div class="chunk-identity"><span class="chunk-number">Chunk ${chunk.chunk_index}</span><span class="tags">${tags.map(tag=>`<span class="tag">${esc(tag)}</span>`).join('')}</span></div><div class="chunk-tools"><div class="chunk-actions"><button class="icon-button" data-copy="${esc(chunk.chunk_id)}">复制正文</button><button class="icon-button" data-link="${esc(chunk.chunk_id)}">定位链接</button></div><span class="chunk-arrow" aria-hidden="true">▶</span></div></header><div class="chunk-collapse" id="${esc(panelId)}" ${open?'':'hidden'}><div class="chunk-body">${highlightStructure(chunk.body_text,query)}</div></div></article>`;
  }).join('');
  const countText=`显示 ${chunks.length} / ${doc.chunk_count} 个 Chunk`;
  document.getElementById('content').innerHTML=`<section class="document-hero"><div class="result-line">${countText}</div><h2>${esc(doc.document_title)}</h2><p class="file-name">${esc(doc.file_name)}</p><dl class="meta">${meta}</dl></section><div class="section-bar"><h3>法规正文切片</h3><p>${countText}</p></div><section class="chunk-list">${cards||'<div class="empty">当前法规中没有匹配的正文</div>'}</section>`;
}

function renderAll(){
  const visible=filteredDocs();
  if(!visible.some(doc=>doc.document_id===activeDocId)){
    activeDocId=visible[0]?.document_id||null;
    expandedAuthority=activeDocId?docMap.get(activeDocId).navigation_authority:null;
    openChunkId=null;
  }
  renderSummary(visible);renderDocList(visible);renderMain(visible);syncUrl();
}
function setOpenChunk(id,{scroll=false}={}){
  openChunkId=openChunkId===id?null:id;
  document.querySelectorAll('[data-chunk-card]').forEach(card=>{
    const open=card.dataset.chunkCard===openChunkId;
    card.classList.toggle('open',open);
    const head=card.querySelector('[data-toggle-chunk]');const panel=card.querySelector('.chunk-collapse');
    head?.setAttribute('aria-expanded',String(open));if(panel)panel.hidden=!open;
  });
  if(scroll&&openChunkId)requestAnimationFrame(()=>document.getElementById(openChunkId)?.scrollIntoView({behavior:'smooth',block:'start'}));
}
function setSidebar(open){document.body.classList.toggle('sidebar-open',open);document.getElementById('mobile-toggle').setAttribute('aria-expanded',String(open))}
function selectDoc(id){if(!docMap.has(id))return;activeDocId=id;expandedAuthority=docMap.get(id).navigation_authority;openChunkId=null;renderAll();setSidebar(false);const url=new URL(location.href);url.hash=id;history.replaceState(null,'',url)}
function showToast(message){const toast=document.getElementById('toast');toast.textContent=message;toast.classList.add('show');clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>toast.classList.remove('show'),1500)}
async function copyText(text,message){try{await navigator.clipboard.writeText(text)}catch(error){const area=document.createElement('textarea');area.value=text;document.body.appendChild(area);area.select();document.execCommand('copy');area.remove()}showToast(message)}

fillSelect(controls.authority,[...new Set(docs.map(doc=>doc.navigation_authority).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN')));
fillSelect(controls.format,[...new Set(docs.map(doc=>doc.source_type).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN')));
Object.entries(controls).forEach(([key,control])=>{control.value=params.get(key)||'';control.addEventListener(control.tagName==='SELECT'?'change':'input',renderAll)});
document.getElementById('mobile-toggle').addEventListener('click',()=>setSidebar(!document.body.classList.contains('sidebar-open')));
document.getElementById('doc-list').addEventListener('click',event=>{
  const docButton=event.target.closest('[data-doc]');if(docButton&&!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey){event.preventDefault();selectDoc(docButton.dataset.doc);return}
  const groupButton=event.target.closest('[data-authority]');if(groupButton){const authority=groupButton.dataset.authority;expandedAuthority=expandedAuthority===authority?null:authority;renderDocList(filteredDocs())}
});
document.getElementById('content').addEventListener('click',event=>{
  const copy=event.target.closest('[data-copy]');if(copy){event.stopPropagation();const chunk=docMap.get(activeDocId)?.chunks.find(item=>item.chunk_id===copy.dataset.copy);if(chunk)copyText(chunk.body_text,'正文已复制');return}
  const link=event.target.closest('[data-link]');if(link){event.stopPropagation();const url=location.href.split('#')[0]+'#'+link.dataset.link;copyText(url,'定位链接已复制');history.replaceState(null,'','#'+link.dataset.link);return}
  const toggle=event.target.closest('[data-toggle-chunk]');if(toggle)setOpenChunk(toggle.dataset.toggleChunk,{scroll:true});
});
document.getElementById('content').addEventListener('keydown',event=>{const toggle=event.target.closest('[data-toggle-chunk]');if(toggle&&(event.key==='Enter'||event.key===' ')){event.preventDefault();setOpenChunk(toggle.dataset.toggleChunk,{scroll:true})}});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setSidebar(false);if(event.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();controls.q.focus()}});

function openHash(){
  const hash=decodeURIComponent(location.hash.slice(1));if(!hash)return;
  const doc=docs.find(item=>item.document_id===hash||item.chunks.some(chunk=>chunk.chunk_id===hash));if(!doc)return;
  activeDocId=doc.document_id;expandedAuthority=doc.navigation_authority;openChunkId=hash.startsWith('chunk_')?hash:null;renderAll();
  if(hash.startsWith('chunk_'))requestAnimationFrame(()=>document.getElementById(hash)?.scrollIntoView({block:'start'}));
}
window.addEventListener('popstate',openHash);
openHash();renderAll();
</script>
</body>
</html>
'''


def main() -> None:
    data = public_data()
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = HTML.replace("__VIEWER_DATA__", serialized)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "documents": data["summary"]["documents"],
                "authorities": data["summary"]["authorities"],
                "chunks": data["summary"]["chunks"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
