#!/usr/bin/env python3
"""Build the standalone, public-safe Chunk viewer from the canonical corpus."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT / "data/processed/chunks/jsonl/all_chunks.jsonl"
OUTPUT_PATH = ROOT / "data/processed/chunk_review_viewer/chunk_review.html"


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


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
                "document_number": chunk.get("document_number", ""),
                "validity_status": chunk.get("validity_status", ""),
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

    return {
        "summary": {
            "documents": len(documents),
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
  --sidebar-bg:#faf9f6;
  --seal:#a4372a;--seal-soft:#f8ebe7;--jade:#2d6a58;--jade-soft:#e7f1ed;
  --gold:#a97828;--shadow:0 14px 40px rgba(22,32,47,.08);
  --ui:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --reading:"STSong","Songti SC","Noto Serif CJK SC","Source Han Serif SC",serif;
  --mono:"SFMono-Regular","Cascadia Code","Liberation Mono",monospace;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--canvas);color:var(--ink);font-family:var(--ui);min-height:100vh}
button,input{font:inherit}
button,a{outline-offset:3px;touch-action:manipulation}
:focus-visible{outline:2px solid var(--seal)}
.skip-link{position:fixed;left:16px;top:10px;z-index:100;padding:9px 12px;background:var(--navy);color:#fff;border-radius:8px;transform:translateY(-150%);transition:transform .16s}.skip-link:focus{transform:none}
.shell{display:grid;grid-template-columns:350px minmax(0,1fr);min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;background:var(--sidebar-bg);color:var(--ink);border-right:1px solid var(--line);display:flex;flex-direction:column;overflow:hidden}
.brand{padding:24px 20px 16px;border-bottom:1px solid var(--line)}
.brand h1{font-family:var(--reading);font-size:21px;line-height:1.38;font-weight:700;color:var(--navy-2);margin:0;letter-spacing:.015em}
.summary{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:16px 20px 14px}
.summary div{padding:11px 12px;background:#fff;border:1px solid var(--line);border-radius:9px}
.summary b{display:block;color:var(--navy-2);font-size:18px;line-height:1.2}.summary span{display:block;margin-top:4px;font-size:10px;color:#6b7280;letter-spacing:.03em}
.search-wrap{padding:0 20px 14px;border-bottom:1px solid var(--line-soft)}
.search{width:100%;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:10px 12px;font-size:12px}
.search::placeholder{color:#8a9099}
.doc-list{overflow:auto;flex:1;padding:10px 10px 20px;scrollbar-width:thin}
.authority-group+ .authority-group{margin-top:5px}
.authority-button{display:flex;align-items:center;width:100%;gap:8px;border:0;background:transparent;color:var(--navy-2);padding:9px 9px;border-radius:8px;cursor:pointer;text-align:left}
.authority-button:hover{background:#f0eee8}
.authority-arrow{width:12px;color:#7b8490;font-size:10px;transition:transform .16s;flex:0 0 auto}.authority-group.open .authority-arrow{transform:rotate(90deg)}
.authority-name{font-size:12px;line-height:1.45;font-weight:700;flex:1;min-width:0}
.authority-count{font-size:10px;color:#7b8490;white-space:nowrap}
.authority-docs{padding-left:12px}
.doc-button{display:flex;width:100%;align-items:flex-start;gap:8px;text-align:left;border:0;border-left:3px solid transparent;background:transparent;color:var(--ink);padding:9px 9px 9px 12px;cursor:pointer;border-radius:0 8px 8px 0;text-decoration:none;transition:background .16s,border-color .16s}
.doc-button:hover{background:#f0eee8}
.doc-button.active{background:#eef2f4;border-left-color:var(--seal)}
.doc-title{font-family:var(--reading);font-size:12px;line-height:1.5;font-weight:600;flex:1;min-width:0}.doc-button.active .doc-title{font-weight:700;color:var(--navy-2)}
.doc-count{font-size:9px;line-height:1.5;color:#7b8490;white-space:nowrap;padding-top:1px}
.show-all{display:block;width:calc(100% - 12px);margin:3px 0 5px 12px;padding:6px 9px;border:0;background:transparent;color:var(--seal);font-size:10px;text-align:left;cursor:pointer;border-radius:6px}.show-all:hover{background:var(--seal-soft)}
.main{min-width:0}
.topbar{position:sticky;top:0;z-index:10;height:64px;background:rgba(243,240,233,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;padding:0 34px}
.mobile-toggle{display:none;border:1px solid var(--line);background:var(--paper);border-radius:8px;padding:7px 10px;cursor:pointer}
.breadcrumb{font-size:11px;letter-spacing:.08em;color:var(--ink-soft);white-space:nowrap}
.page-link{color:var(--seal);font-size:11px;text-decoration:none;border-bottom:1px solid rgba(164,55,42,.24);white-space:nowrap}.page-link:hover{border-bottom-color:var(--seal)}
.chunk-search{margin-left:auto;width:min(320px,40vw);border:1px solid var(--line);background:rgba(255,253,248,.88);border-radius:9px;padding:9px 12px;color:var(--ink);font-size:12px}
.content{max-width:1180px;margin:0 auto;padding:38px 42px 80px}
.document-hero{position:relative;background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:28px 30px 24px;box-shadow:var(--shadow);overflow:hidden}
.document-hero::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--seal)}
.result-line{display:flex;align-items:center;gap:8px;color:var(--jade);font-size:11px;font-weight:700;letter-spacing:.08em;margin-bottom:12px}
.result-line::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--jade);box-shadow:0 0 0 4px var(--jade-soft)}
.document-hero h2{font-family:var(--reading);font-size:27px;line-height:1.38;margin:0;letter-spacing:.015em}
.file-name{font-size:11px;color:var(--ink-soft);margin:8px 0 0}
.meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px 24px;margin:22px 0 0;padding-top:18px;border-top:1px solid var(--line-soft)}
.meta div{min-width:0}.meta dt{font-size:10px;color:#7f7568;letter-spacing:.1em;margin-bottom:4px}.meta dd{font-size:12px;line-height:1.5;margin:0;word-break:break-word}
.meta a{color:var(--seal);text-decoration:none;border-bottom:1px solid rgba(164,55,42,.25)}
.section-bar{display:flex;align-items:end;justify-content:space-between;gap:20px;margin:34px 2px 14px}
.section-bar h3{font-family:var(--reading);font-size:20px;margin:0}.section-bar p{font-size:11px;color:var(--ink-soft);margin:0}
.chunk-list{display:grid;gap:14px}
.chunk-card{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 5px 18px rgba(22,32,47,.045);animation:rise .28s ease both;content-visibility:auto;contain-intrinsic-size:520px}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
.chunk-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:13px 18px;background:#faf7f1;border-bottom:1px solid var(--line-soft)}
.chunk-identity{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.chunk-number{font-family:var(--reading);font-weight:700;color:var(--seal)}
.tags{display:flex;gap:5px;flex-wrap:wrap}
.tag{font-size:10px;color:var(--navy-2);background:#e9eef3;border-radius:999px;padding:3px 7px}
.chunk-actions{display:flex;gap:6px;flex-shrink:0}
.icon-button{border:1px solid var(--line);background:var(--paper);color:var(--ink-soft);border-radius:7px;padding:5px 8px;font-size:10px;cursor:pointer}
.icon-button:hover{border-color:#b8ac9a;color:var(--seal)}
.chunk-body{font-family:var(--reading);font-size:15px;line-height:2.05;white-space:pre-wrap;word-break:break-word;padding:22px 24px 26px;color:#26354a}
.hl-chapter{display:inline-block;color:var(--seal);font-size:1.08em;font-weight:700;margin-top:.3em}.hl-article{color:var(--navy-2);font-weight:700}.hl-section{color:var(--jade);font-weight:700}.hl-item{color:#8b621f;font-weight:700}.hl-attachment{color:var(--seal);font-weight:700}
.match{background:#f4dc9f;color:#33250b;border-radius:2px;padding:0 1px}
.empty{padding:70px 24px;text-align:center;background:var(--paper);border:1px dashed var(--line);border-radius:14px;color:var(--ink-soft)}
.toast{position:fixed;right:24px;bottom:24px;background:var(--navy);color:#fff;padding:10px 14px;border-radius:9px;font-size:11px;opacity:0;transform:translateY(8px);pointer-events:none;transition:.2s}.toast.show{opacity:1;transform:none}
@media(max-width:900px){.shell{grid-template-columns:300px minmax(0,1fr)}.content{padding:28px 24px 70px}.meta{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.shell{display:block}.sidebar{position:fixed;z-index:30;left:0;top:0;width:min(88vw,350px);transform:translateX(-105%);transition:transform .22s;box-shadow:20px 0 60px rgba(0,0,0,.18);overscroll-behavior:contain}body.sidebar-open .sidebar{transform:none}.mobile-toggle{display:inline-block}.topbar{padding:0 14px;height:58px}.breadcrumb{display:none}.chunk-search{width:auto;flex:1}.content{padding:20px 14px 60px}.document-hero{padding:23px 20px}.document-hero h2{font-size:22px}.meta{grid-template-columns:1fr}.chunk-head{align-items:center}.chunk-body{padding:18px;font-size:14px}.section-bar{align-items:flex-start;flex-direction:column;gap:4px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">跳到法规正文</a>
<div class="shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand"><h1>中国场外衍生品<br>法规知识库</h1></div>
    <div class="summary"><div><b id="document-count">—</b><span>法规数量</span></div><div><b id="chunk-count">—</b><span>Chunks数量</span></div></div>
    <div class="search-wrap"><input class="search" id="doc-search" name="document-search" type="search" placeholder="搜索法规、章节或条文…" aria-label="搜索法规、章节或条文" autocomplete="off" spellcheck="false"></div>
    <nav class="doc-list" id="doc-list" aria-label="按发文主体分组的法规目录"></nav>
  </aside>
  <main class="main" id="main-content">
    <header class="topbar"><button class="mobile-toggle" id="mobile-toggle" aria-label="打开法规列表" aria-controls="sidebar" aria-expanded="false">目录</button><div class="breadcrumb">法规知识库 / Chunk 切分查看</div><a class="page-link" href="regulation_catalog.html">监管文件总目录</a><input class="chunk-search" id="chunk-search" name="chunk-search" type="search" placeholder="在当前法规正文中搜索…" aria-label="搜索当前法规正文" autocomplete="off" spellcheck="false"></header>
    <div class="content" id="content" aria-live="polite"></div>
  </main>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="viewer-data">__VIEWER_DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('viewer-data').textContent);
const docs=DATA.documents;
const docMap=new Map(docs.map(doc=>[doc.document_id,doc]));
let activeDocId=docs.length?docs[0].document_id:null;
const initialParams=new URLSearchParams(location.search);
let bodyQuery=initialParams.get('text')||'';
const authorityOf=doc=>(doc.issuing_authority||'').trim()||'其他监管机构';
const expandedAuthorities=new Set(activeDocId?[authorityOf(docMap.get(activeDocId))]:[]);
const expandedDocGroups=new Set();

const esc=value=>String(value??'').replace(/[&<>"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
const normalize=value=>String(value??'').toLowerCase();
const articleLabel=chunk=>chunk.article_start?(chunk.article_end&&chunk.article_end!==chunk.article_start?chunk.article_start+'–'+chunk.article_end:chunk.article_start):'';

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

function renderSummary(){
  document.getElementById('document-count').textContent=DATA.summary.documents;
  document.getElementById('chunk-count').textContent=DATA.summary.chunks;
}

function renderDocList(){
  const query=normalize(document.getElementById('doc-search').value);
  const matches=doc=>!query||normalize([
    doc.document_title,doc.document_number,doc.issuing_authority,doc.file_name,
    ...doc.chunks.flatMap(chunk=>[chunk.body_text,articleLabel(chunk),chunk.chapter_title,chunk.section_title,chunk.part_title,chunk.attachment_name])
  ].join(' ')).includes(query);
  const grouped=new Map();
  docs.filter(matches).forEach(doc=>{const authority=authorityOf(doc);if(!grouped.has(authority))grouped.set(authority,[]);grouped.get(authority).push(doc)});
  const html=[...grouped].map(([authority,groupDocs])=>{
    const open=query||expandedAuthorities.has(authority);
    let visibleDocs=groupDocs;
    if(!query&&!expandedDocGroups.has(authority)&&groupDocs.length>6){
      visibleDocs=groupDocs.slice(0,6);
      const active=groupDocs.find(doc=>doc.document_id===activeDocId);
      if(active&&!visibleDocs.includes(active))visibleDocs=[...groupDocs.slice(0,5),active];
    }
    const docsHtml=open?`<div class="authority-docs">${visibleDocs.map(doc=>`<a href="#${esc(doc.document_id)}" class="doc-button ${doc.document_id===activeDocId?'active':''}" data-doc="${esc(doc.document_id)}"><span class="doc-title">${esc(doc.document_title)}</span><span class="doc-count">${doc.chunk_count} 个</span></a>`).join('')}${!query&&groupDocs.length>6?`<button class="show-all" data-show-all="${esc(authority)}">${expandedDocGroups.has(authority)?'收起多余条目':`查看全部 ${groupDocs.length} 项`}</button>`:''}</div>`:'';
    return `<section class="authority-group ${open?'open':''}"><button class="authority-button" data-authority="${esc(authority)}" aria-expanded="${open?'true':'false'}"><span class="authority-arrow" aria-hidden="true">▶</span><span class="authority-name">${esc(authority)}</span><span class="authority-count">${groupDocs.length}部法规</span></button>${docsHtml}</section>`;
  }).join('');
  document.getElementById('doc-list').innerHTML=html||'<div class="empty">没有匹配的法规</div>';
}

function metaItem(label,value,html=false){return value?`<div><dt>${label}</dt><dd>${html?value:esc(value)}</dd></div>`:''}

function renderMain(){
  const doc=docMap.get(activeDocId);if(!doc){document.getElementById('content').innerHTML='<div class="empty">暂无法规数据</div>';return}
  const query=normalize(bodyQuery);
  const chunks=doc.chunks.filter(chunk=>!query||normalize([chunk.body_text,articleLabel(chunk),chunk.chapter_title,chunk.section_title,chunk.part_title,chunk.attachment_name].join(' ')).includes(query));
  const official=doc.official_url?`<a href="${esc(doc.official_url)}" target="_blank" rel="noopener noreferrer">查看官方原文</a>`:'';
  const meta=[
    metaItem('文号',doc.document_number),metaItem('发文机关',doc.issuing_authority),metaItem('效力状态',doc.validity_status),
    metaItem('发布日期',doc.publication_date),metaItem('施行日期',doc.effective_date),metaItem('权威来源',official,true)
  ].join('');
  const cards=chunks.map((chunk,index)=>{
    const tags=[articleLabel(chunk),chunk.chapter_title,chunk.section_title,chunk.part_title,chunk.attachment_name].filter(Boolean);
    return `<article class="chunk-card" id="${esc(chunk.chunk_id)}" style="animation-delay:${Math.min(index*18,180)}ms"><header class="chunk-head"><div class="chunk-identity"><span class="chunk-number">Chunk ${chunk.chunk_index}</span><span class="tags">${tags.map(tag=>`<span class="tag">${esc(tag)}</span>`).join('')}</span></div><div class="chunk-actions"><button class="icon-button" data-copy="${esc(chunk.chunk_id)}">复制正文</button><button class="icon-button" data-link="${esc(chunk.chunk_id)}">定位链接</button></div></header><div class="chunk-body">${highlightStructure(chunk.body_text,bodyQuery)}</div></article>`;
  }).join('');
  const resultLabel=`${doc.chunk_count} 个 Chunk`;
  document.getElementById('content').innerHTML=`<section class="document-hero"><div class="result-line">${resultLabel}</div><h2>${esc(doc.document_title)}</h2><p class="file-name">${esc(doc.file_name)}</p><dl class="meta">${meta}</dl></section><div class="section-bar"><h3>法规正文切片</h3><p>显示 ${chunks.length} / ${doc.chunk_count} 个 Chunk</p></div><section class="chunk-list">${cards||'<div class="empty">当前法规中没有匹配的正文</div>'}</section>`;
}

function setParam(name,value){const url=new URL(location.href);value?url.searchParams.set(name,value):url.searchParams.delete(name);history.replaceState(null,'',url)}
function setSidebar(open){document.body.classList.toggle('sidebar-open',open);document.getElementById('mobile-toggle').setAttribute('aria-expanded',String(open))}
function selectDoc(id){if(!docMap.has(id))return;activeDocId=id;expandedAuthorities.add(authorityOf(docMap.get(id)));bodyQuery='';document.getElementById('chunk-search').value='';setParam('text','');renderDocList();renderMain();setSidebar(false);const url=new URL(location.href);url.hash=id;history.replaceState(null,'',url)}
function showToast(message){const toast=document.getElementById('toast');toast.textContent=message;toast.classList.add('show');clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>toast.classList.remove('show'),1500)}
async function copyText(text,message){try{await navigator.clipboard.writeText(text)}catch(error){const area=document.createElement('textarea');area.value=text;document.body.appendChild(area);area.select();document.execCommand('copy');area.remove()}showToast(message)}

document.getElementById('doc-search').value=initialParams.get('q')||'';
document.getElementById('chunk-search').value=bodyQuery;
let docSearchTimer;
document.getElementById('doc-search').addEventListener('input',event=>{clearTimeout(docSearchTimer);docSearchTimer=setTimeout(()=>{setParam('q',event.target.value.trim());renderDocList()},120)});
document.getElementById('chunk-search').addEventListener('input',event=>{bodyQuery=event.target.value.trim();setParam('text',bodyQuery);renderMain()});
document.getElementById('mobile-toggle').addEventListener('click',()=>setSidebar(!document.body.classList.contains('sidebar-open')));
document.getElementById('doc-list').addEventListener('click',event=>{
  const docButton=event.target.closest('[data-doc]');if(docButton&&!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey){event.preventDefault();selectDoc(docButton.dataset.doc);return}
  const groupButton=event.target.closest('[data-authority]');if(groupButton){const authority=groupButton.dataset.authority;expandedAuthorities.has(authority)?expandedAuthorities.delete(authority):expandedAuthorities.add(authority);renderDocList();return}
  const showAll=event.target.closest('[data-show-all]');if(showAll){const authority=showAll.dataset.showAll;expandedDocGroups.has(authority)?expandedDocGroups.delete(authority):expandedDocGroups.add(authority);expandedAuthorities.add(authority);renderDocList()}
});
document.getElementById('content').addEventListener('click',event=>{
  const copy=event.target.closest('[data-copy]');if(copy){const doc=docMap.get(activeDocId);const chunk=doc.chunks.find(item=>item.chunk_id===copy.dataset.copy);if(chunk)copyText(chunk.body_text,'正文已复制');return}
  const link=event.target.closest('[data-link]');if(link){const url=location.href.split('#')[0]+'#'+link.dataset.link;copyText(url,'定位链接已复制');history.replaceState(null,'','#'+link.dataset.link)}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setSidebar(false);if(event.key==='/'&&document.activeElement.tagName!=='INPUT'){event.preventDefault();document.getElementById('chunk-search').focus()}});

function openHash(){const hash=decodeURIComponent(location.hash.slice(1));if(!hash)return;const doc=docs.find(item=>item.document_id===hash||item.chunks.some(chunk=>chunk.chunk_id===hash));if(!doc)return;activeDocId=doc.document_id;expandedAuthorities.add(authorityOf(doc));renderDocList();renderMain();if(hash.startsWith('chunk_'))requestAnimationFrame(()=>document.getElementById(hash)?.scrollIntoView({block:'center'}))}
window.addEventListener('popstate',openHash);
renderSummary();renderDocList();renderMain();openHash();
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
                "chunks": data["summary"]["chunks"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
