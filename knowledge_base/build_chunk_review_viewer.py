#!/usr/bin/env python3
"""Build the standalone, public-safe Chunk review result viewer."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT / "data/processed/chunks/jsonl/all_chunks.jsonl"
REVIEW_PATH = ROOT / "data/processed/chunk_review_independent/chunk_review.jsonl"
COVERAGE_PATH = ROOT / "data/processed/chunk_review_independent/coverage.json"
OUTPUT_PATH = ROOT / "data/processed/chunk_review_viewer/chunk_review.html"


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def public_data() -> dict:
    chunks = read_jsonl(CHUNKS_PATH)
    reviews = {row["chunk_id"]: row for row in read_jsonl(REVIEW_PATH)}
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    documents: OrderedDict[str, dict] = OrderedDict()
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("all_chunks.jsonl contains duplicate chunk_id values")
    missing_reviews = set(chunk_ids) - set(reviews)
    extra_reviews = set(reviews) - set(chunk_ids)
    if missing_reviews or extra_reviews:
        raise ValueError(
            f"review coverage mismatch: missing={len(missing_reviews)}, extra={len(extra_reviews)}"
        )

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
        review = reviews[chunk["chunk_id"]]
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
                "status": review["status"],
            }
        )

    for document in documents.values():
        document["chunks"].sort(key=lambda item: item["chunk_index"])
        document["chunk_count"] = len(document["chunks"])
        document["review_status"] = (
            "PASS" if all(chunk["status"] == "PASS" for chunk in document["chunks"]) else "ISSUE"
        )

    return {
        "summary": {
            "documents": len(documents),
            "chunks": len(chunks),
            "reviewed": coverage.get("review_record_count", len(reviews)),
            "pass": coverage.get("PASS", 0),
            "issues": sum(coverage.get(level, 0) for level in ("MINOR", "MAJOR", "CRITICAL")),
        },
        "documents": list(documents.values()),
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="中国场外衍生品法规知识库 Chunk 复核结果浏览器">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%2310233f'/%3E%3Cpath d='M18 44h28M32 13v31M20 20h24M20 20l-8 15h16L20 20zm24 0-8 15h16L44 20z' fill='none' stroke='%23d6aa5a' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<title>中国场外衍生品法规知识库 · Chunk 复核结果</title>
<style>
:root{
  --ink:#152238;--ink-soft:#536074;--paper:#fffdf8;--canvas:#f3f0e9;
  --navy:#10233f;--navy-2:#1a3558;--line:#dcd6ca;--line-soft:#ebe6dc;
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
button,a{outline-offset:3px}
:focus-visible{outline:2px solid var(--seal)}
.shell{display:grid;grid-template-columns:350px minmax(0,1fr);min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;background:var(--navy);color:#f5f1e8;display:flex;flex-direction:column;overflow:hidden}
.brand{padding:28px 24px 20px;border-bottom:1px solid rgba(255,255,255,.1)}
.eyebrow{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#c9bfae;margin:0 0 10px}
.brand h1{font-family:var(--reading);font-size:22px;line-height:1.35;font-weight:700;margin:0;letter-spacing:.02em}
.brand p{font-size:12px;line-height:1.65;color:#aeb9c8;margin:10px 0 0}
.quality{margin:18px 20px 14px;padding:14px 15px;background:rgba(255,255,255,.065);border:1px solid rgba(255,255,255,.1);border-radius:12px}
.quality-head{display:flex;justify-content:space-between;align-items:center;gap:12px}
.quality strong{font-size:18px;color:#fff}
.quality .stamp{color:#d9f0e7;background:rgba(45,106,88,.45);border:1px solid rgba(170,222,202,.28);border-radius:999px;padding:4px 9px;font-size:11px}
.quality p{margin:8px 0 0;color:#aeb9c8;font-size:11px;line-height:1.55}
.summary{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0 20px 16px}
.summary div{padding:10px 11px;border-top:1px solid rgba(255,255,255,.12)}
.summary b{display:block;color:#fff;font-size:17px}.summary span{font-size:10px;color:#98a6b8;letter-spacing:.08em}
.search-wrap{padding:0 20px 14px}
.search{width:100%;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.07);color:#fff;border-radius:9px;padding:10px 12px;font-size:12px}
.search::placeholder{color:#8392a7}
.doc-list{overflow:auto;flex:1;padding:0 10px 20px;scrollbar-width:thin}
.doc-button{display:block;width:100%;text-align:left;border:0;border-left:3px solid transparent;background:transparent;color:#dae1ea;padding:11px 13px 11px 14px;cursor:pointer;border-radius:0 9px 9px 0;transition:background .16s,border-color .16s}
.doc-button:hover{background:rgba(255,255,255,.055)}
.doc-button.active{background:rgba(255,255,255,.1);border-left-color:#d6aa5a}
.doc-title{font-family:var(--reading);font-size:13px;line-height:1.48;font-weight:700}
.doc-sub{display:flex;justify-content:space-between;gap:10px;margin-top:5px;color:#93a1b3;font-size:10px}
.main{min-width:0}
.topbar{position:sticky;top:0;z-index:10;height:64px;background:rgba(243,240,233,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;padding:0 34px}
.mobile-toggle{display:none;border:1px solid var(--line);background:var(--paper);border-radius:8px;padding:7px 10px;cursor:pointer}
.breadcrumb{font-size:11px;letter-spacing:.08em;color:var(--ink-soft);white-space:nowrap}
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
.chunk-card{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 5px 18px rgba(22,32,47,.045);animation:rise .28s ease both}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
.chunk-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:13px 18px;background:#faf7f1;border-bottom:1px solid var(--line-soft)}
.chunk-identity{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.chunk-number{font-family:var(--reading);font-weight:700;color:var(--seal)}
.chunk-id{font-family:var(--mono);font-size:10px;color:#746b61}
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
@media(max-width:700px){.shell{display:block}.sidebar{position:fixed;z-index:30;left:0;top:0;width:min(88vw,350px);transform:translateX(-105%);transition:transform .22s;box-shadow:20px 0 60px rgba(0,0,0,.24)}body.sidebar-open .sidebar{transform:none}.mobile-toggle{display:inline-block}.topbar{padding:0 14px;height:58px}.breadcrumb{display:none}.chunk-search{width:auto;flex:1}.content{padding:20px 14px 60px}.document-hero{padding:23px 20px}.document-hero h2{font-size:22px}.meta{grid-template-columns:1fr}.chunk-head{align-items:center}.chunk-id{display:none}.chunk-body{padding:18px;font-size:14px}.section-bar{align-items:flex-start;flex-direction:column;gap:4px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand"><p class="eyebrow">Regulatory Knowledge Base</p><h1>中国场外衍生品<br>法规知识库</h1><p>结构化法规与 Chunk 复核结果浏览器</p></div>
    <div class="quality"><div class="quality-head"><strong id="reviewed-count">—</strong><span class="stamp" id="review-stamp">—</span></div><p id="review-summary">正在读取复核结果。</p></div>
    <div class="summary"><div><b id="document-count">—</b><span>正式法规</span></div><div><b id="chunk-count">—</b><span>CHUNKS</span></div></div>
    <div class="search-wrap"><input class="search" id="doc-search" type="search" placeholder="搜索法规、文号或机关" aria-label="搜索法规"></div>
    <nav class="doc-list" id="doc-list" aria-label="法规列表"></nav>
  </aside>
  <main class="main">
    <header class="topbar"><button class="mobile-toggle" id="mobile-toggle" aria-label="打开法规列表">目录</button><div class="breadcrumb">法规知识库 / Chunk 复核结果</div><input class="chunk-search" id="chunk-search" type="search" placeholder="在当前法规正文中搜索" aria-label="搜索当前法规正文"></header>
    <div class="content" id="content"></div>
  </main>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="viewer-data">__VIEWER_DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('viewer-data').textContent);
const docs=DATA.documents;
const docMap=new Map(docs.map(doc=>[doc.document_id,doc]));
let activeDocId=docs.length?docs[0].document_id:null;
let bodyQuery='';

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
  document.getElementById('reviewed-count').textContent=DATA.summary.reviewed+'/'+DATA.summary.chunks;
  document.getElementById('document-count').textContent=DATA.summary.documents;
  document.getElementById('chunk-count').textContent=DATA.summary.chunks;
  const passed=DATA.summary.reviewed===DATA.summary.chunks&&DATA.summary.issues===0&&DATA.summary.pass===DATA.summary.chunks;
  document.getElementById('review-stamp').textContent=passed?'复核通过':'存在问题';
  document.getElementById('review-summary').textContent=passed?'全部 Chunk 已完成独立复核，未发现正文遗漏、转换错误或切分错误。':`已复核 ${DATA.summary.reviewed} 个 Chunk，其中 ${DATA.summary.issues} 个需要关注。`;
}

function renderDocList(){
  const query=normalize(document.getElementById('doc-search').value);
  const visible=docs.filter(doc=>normalize([doc.document_title,doc.document_number,doc.issuing_authority,doc.file_name].join(' ')).includes(query));
  document.getElementById('doc-list').innerHTML=visible.length?visible.map(doc=>`<button class="doc-button ${doc.document_id===activeDocId?'active':''}" data-doc="${esc(doc.document_id)}"><span class="doc-title">${esc(doc.document_title)}</span><span class="doc-sub"><span>${esc(doc.issuing_authority||'发文机关未载')}</span><span>${doc.chunk_count} Chunk</span></span></button>`).join(''):'<div class="empty">没有匹配的法规</div>';
}

function metaItem(label,value,html=false){return value?`<div><dt>${label}</dt><dd>${html?value:esc(value)}</dd></div>`:''}

function renderMain(){
  const doc=docMap.get(activeDocId);if(!doc){document.getElementById('content').innerHTML='<div class="empty">暂无法规数据</div>';return}
  const query=normalize(bodyQuery);
  const chunks=doc.chunks.filter(chunk=>!query||normalize([chunk.chunk_id,chunk.body_text,articleLabel(chunk),chunk.chapter_title,chunk.section_title].join(' ')).includes(query));
  const official=doc.official_url?`<a href="${esc(doc.official_url)}" target="_blank" rel="noopener noreferrer">查看官方原文</a>`:'';
  const meta=[
    metaItem('文号',doc.document_number),metaItem('发文机关',doc.issuing_authority),metaItem('效力状态',doc.validity_status),
    metaItem('发布日期',doc.publication_date),metaItem('施行日期',doc.effective_date),metaItem('权威来源',official,true)
  ].join('');
  const cards=chunks.map((chunk,index)=>{
    const tags=[articleLabel(chunk),chunk.chapter_title,chunk.section_title,chunk.part_title,chunk.attachment_name].filter(Boolean);
    return `<article class="chunk-card" id="${esc(chunk.chunk_id)}" style="animation-delay:${Math.min(index*18,180)}ms"><header class="chunk-head"><div class="chunk-identity"><span class="chunk-number">Chunk ${chunk.chunk_index}</span><code class="chunk-id">${esc(chunk.chunk_id)}</code><span class="tags">${tags.map(tag=>`<span class="tag">${esc(tag)}</span>`).join('')}</span></div><div class="chunk-actions"><button class="icon-button" data-copy="${esc(chunk.chunk_id)}">复制正文</button><button class="icon-button" data-link="${esc(chunk.chunk_id)}">定位链接</button></div></header><div class="chunk-body">${highlightStructure(chunk.body_text,bodyQuery)}</div></article>`;
  }).join('');
  const resultLabel=doc.review_status==='PASS'?'独立复核通过':'复核发现问题';
  document.getElementById('content').innerHTML=`<section class="document-hero"><div class="result-line">${resultLabel}</div><h2>${esc(doc.document_title)}</h2><p class="file-name">${esc(doc.file_name)}</p><dl class="meta">${meta}</dl></section><div class="section-bar"><h3>法规正文切片</h3><p>显示 ${chunks.length} / ${doc.chunk_count} 个 Chunk</p></div><section class="chunk-list">${cards||'<div class="empty">当前法规中没有匹配的正文</div>'}</section>`;
}

function selectDoc(id){if(!docMap.has(id))return;activeDocId=id;bodyQuery='';document.getElementById('chunk-search').value='';renderDocList();renderMain();document.body.classList.remove('sidebar-open');history.replaceState(null,'','#'+id)}
function showToast(message){const toast=document.getElementById('toast');toast.textContent=message;toast.classList.add('show');clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>toast.classList.remove('show'),1500)}
async function copyText(text,message){try{await navigator.clipboard.writeText(text)}catch(error){const area=document.createElement('textarea');area.value=text;document.body.appendChild(area);area.select();document.execCommand('copy');area.remove()}showToast(message)}

document.getElementById('doc-search').addEventListener('input',renderDocList);
document.getElementById('chunk-search').addEventListener('input',event=>{bodyQuery=event.target.value.trim();renderMain()});
document.getElementById('mobile-toggle').addEventListener('click',()=>document.body.classList.toggle('sidebar-open'));
document.getElementById('doc-list').addEventListener('click',event=>{const button=event.target.closest('[data-doc]');if(button)selectDoc(button.dataset.doc)});
document.getElementById('content').addEventListener('click',event=>{
  const copy=event.target.closest('[data-copy]');if(copy){const doc=docMap.get(activeDocId);const chunk=doc.chunks.find(item=>item.chunk_id===copy.dataset.copy);if(chunk)copyText(chunk.body_text,'正文已复制');return}
  const link=event.target.closest('[data-link]');if(link){const url=location.href.split('#')[0]+'#'+link.dataset.link;copyText(url,'定位链接已复制');history.replaceState(null,'','#'+link.dataset.link)}
});
document.addEventListener('keydown',event=>{if(event.key==='/'&&document.activeElement.tagName!=='INPUT'){event.preventDefault();document.getElementById('chunk-search').focus()}});

function openHash(){const hash=decodeURIComponent(location.hash.slice(1));if(!hash)return;const doc=docs.find(item=>item.document_id===hash||item.chunks.some(chunk=>chunk.chunk_id===hash));if(!doc)return;activeDocId=doc.document_id;renderDocList();renderMain();if(hash.startsWith('chunk_'))requestAnimationFrame(()=>document.getElementById(hash)?.scrollIntoView({block:'center'}))}
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
                "reviewed": data["summary"]["reviewed"],
                "issues": data["summary"]["issues"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
