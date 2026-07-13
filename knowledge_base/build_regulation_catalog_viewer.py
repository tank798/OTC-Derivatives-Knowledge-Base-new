#!/usr/bin/env python3
"""Build the standalone regulatory document catalog from the current corpus."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "data/index/document_metadata.jsonl"
OUTPUT_PATH = ROOT / "data/processed/chunk_review_viewer/regulation_catalog.html"


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def local_href(repository_path: str) -> str:
    path = Path(repository_path)
    try:
        relative = path.relative_to("data")
    except ValueError:
        return ""
    target = Path("../..") / relative
    return quote(target.as_posix(), safe="/()（）—_-.[]")


def public_data() -> dict:
    documents = read_jsonl(METADATA_PATH)
    document_ids = [row.get("document_id", "") for row in documents]
    if not documents:
        raise ValueError("document metadata is empty")
    if not all(document_ids) or len(document_ids) != len(set(document_ids)):
        raise ValueError("document metadata contains empty or duplicate document_id values")

    public_documents: list[dict] = []
    for row in documents:
        public_documents.append({
            "document_id": row["document_id"],
            "document_title": row.get("document_title", ""),
            "file_name": row.get("file_name", ""),
            "issuing_authority": row.get("issuing_authority", "") or "其他监管机构",
            "document_number": row.get("document_number", ""),
            "publication_date": row.get("publication_date", ""),
            "effective_date": row.get("effective_date", ""),
            "validity_status": row.get("validity_status", "") or "状态未载",
            "version": row.get("version", ""),
            "source_type": row.get("source_type", "").upper(),
            "official_url": row.get("official_url", ""),
            "local_href": local_href(row.get("local_file_path", "")),
            "chunk_count": row.get("chunk_count", 0),
            "character_count": row.get("character_count", 0),
            "file_size": row.get("file_size", 0),
        })

    public_documents.sort(
        key=lambda row: (
            row["issuing_authority"],
            row["publication_date"],
            row["document_title"],
        )
    )
    authorities = sorted({row["issuing_authority"] for row in public_documents})
    return {
        "summary": {
            "documents": len(public_documents),
            "authorities": len(authorities),
            "chunks": sum(row["chunk_count"] for row in public_documents),
        },
        "documents": public_documents,
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="中国场外衍生品法规知识库监管文件总目录">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%2310233f'/%3E%3Cpath d='M18 44h28M32 13v31M20 20h24M20 20l-8 15h16L20 20zm24 0-8 15h16L44 20z' fill='none' stroke='%23d6aa5a' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<title>中国场外衍生品法规知识库 · 监管文件总目录</title>
<style>
:root{
  --ink:#152238;--ink-soft:#536074;--paper:#fffdf8;--canvas:#f3f0e9;
  --navy:#10233f;--navy-2:#1a3558;--line:#dcd6ca;--line-soft:#ebe6dc;
  --sidebar-bg:#faf9f6;--seal:#a4372a;--seal-soft:#f8ebe7;
  --jade:#2d6a58;--jade-soft:#e7f1ed;--gold:#a97828;
  --shadow:0 14px 40px rgba(22,32,47,.08);
  --ui:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --reading:"STSong","Songti SC","Noto Serif CJK SC","Source Han Serif SC",serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--canvas);color:var(--ink);font-family:var(--ui);min-height:100vh}
button,input,select{font:inherit}button,a{outline-offset:3px;touch-action:manipulation}:focus-visible{outline:2px solid var(--seal)}
.skip-link{position:fixed;left:16px;top:10px;z-index:100;padding:9px 12px;background:var(--navy);color:#fff;border-radius:8px;transform:translateY(-150%);transition:transform .16s}.skip-link:focus{transform:none}
.shell{display:grid;grid-template-columns:350px minmax(0,1fr);min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;background:var(--sidebar-bg);border-right:1px solid var(--line);display:flex;flex-direction:column;overflow:hidden}
.brand{padding:24px 20px 16px;border-bottom:1px solid var(--line)}
.brand h1{font-family:var(--reading);font-size:21px;line-height:1.38;font-weight:700;color:var(--navy-2);margin:0;letter-spacing:.015em}
.summary{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:16px 20px 14px}
.summary div{padding:11px 12px;background:#fff;border:1px solid var(--line);border-radius:9px}
.summary b{display:block;color:var(--navy-2);font-size:18px;line-height:1.2;font-variant-numeric:tabular-nums}.summary span{display:block;margin-top:4px;font-size:10px;color:#6b7280;letter-spacing:.03em}
.sidebar-search{padding:0 20px 14px;border-bottom:1px solid var(--line-soft)}
.search{width:100%;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:10px 12px;font-size:12px}
.search::placeholder{color:#8a9099}.authority-list{overflow:auto;flex:1;padding:10px 10px 20px;scrollbar-width:thin}
.authority-link{display:flex;align-items:center;gap:8px;color:var(--navy-2);padding:9px 10px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:700}
.authority-link:hover{background:#f0eee8}.authority-link.active{background:#eef2f4;color:var(--seal)}.authority-link span:first-child{flex:1;min-width:0}.authority-link small{color:#7b8490;font-weight:500;font-variant-numeric:tabular-nums}
.main{min-width:0}.topbar{position:sticky;top:0;z-index:10;height:64px;background:rgba(243,240,233,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;padding:0 34px}
.mobile-toggle{display:none;border:1px solid var(--line);background:var(--paper);border-radius:8px;padding:7px 10px;cursor:pointer}.breadcrumb{font-size:11px;letter-spacing:.08em;color:var(--ink-soft);white-space:nowrap}.page-link{margin-left:auto;color:var(--seal);font-size:11px;text-decoration:none;border-bottom:1px solid rgba(164,55,42,.24);white-space:nowrap}.page-link:hover{border-bottom-color:var(--seal)}
.content{max-width:1280px;margin:0 auto;padding:38px 42px 80px}.hero{position:relative;background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:30px;box-shadow:var(--shadow);overflow:hidden}.hero::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--seal)}
.hero-kicker{color:var(--jade);font-size:11px;font-weight:700;letter-spacing:.12em;margin:0 0 10px}.hero h2{font-family:var(--reading);font-size:30px;line-height:1.35;margin:0;text-wrap:balance}.hero p{max-width:760px;color:var(--ink-soft);font-size:13px;line-height:1.75;margin:10px 0 0;text-wrap:pretty}
.filters{display:grid;grid-template-columns:minmax(220px,1.6fr) repeat(3,minmax(150px,.7fr));gap:10px;margin-top:22px;padding-top:20px;border-top:1px solid var(--line-soft)}
.field{min-width:0}.field label{display:block;font-size:10px;color:#7f7568;letter-spacing:.08em;margin:0 0 5px}.field input,.field select{width:100%;height:40px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);padding:0 11px;font-size:12px}.field select{appearance:auto}
.result-bar{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:34px 2px 14px}.result-bar h3{font-family:var(--reading);font-size:20px;margin:0}.result-bar p{font-size:11px;color:var(--ink-soft);margin:0;font-variant-numeric:tabular-nums}
.group{scroll-margin-top:82px;margin-top:18px}.group-title{display:flex;align-items:center;gap:12px;padding:0 2px 10px;border-bottom:1px solid var(--line)}.group-title h4{font-family:var(--reading);font-size:17px;color:var(--navy-2);margin:0}.group-title span{font-size:10px;color:#7b8490}.document-list{display:grid;gap:10px;margin-top:10px}
.document-card{background:var(--paper);border:1px solid var(--line);border-radius:13px;padding:17px 18px;box-shadow:0 4px 14px rgba(22,32,47,.04);content-visibility:auto;contain-intrinsic-size:190px;animation:rise .24s ease both;scroll-margin-top:82px}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.document-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.document-title{font-family:var(--reading);font-size:17px;line-height:1.55;color:var(--navy-2);margin:0;text-wrap:pretty}.status{display:inline-flex;align-items:center;flex:0 0 auto;padding:4px 8px;border-radius:999px;background:var(--jade-soft);color:var(--jade);font-size:10px;font-weight:700}.status.pending{background:#f7edda;color:#8b621f}.status.unknown{background:#eceff2;color:#66707d}
.document-number{font-size:11px;color:var(--ink-soft);margin:5px 0 0}.document-meta{display:grid;grid-template-columns:1.25fr repeat(4,minmax(100px,.7fr));gap:12px 18px;margin:15px 0 0;padding-top:13px;border-top:1px solid var(--line-soft)}.document-meta div{min-width:0}.document-meta dt{font-size:9px;color:#887d70;letter-spacing:.08em;margin-bottom:4px}.document-meta dd{font-size:11px;line-height:1.5;margin:0;word-break:break-word;font-variant-numeric:tabular-nums}
.actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:15px}.action{display:inline-flex;align-items:center;justify-content:center;min-height:32px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;color:var(--ink-soft);background:#fff;text-decoration:none;font-size:10px}.action:hover{border-color:#b8ac9a;color:var(--seal)}.action.primary{background:var(--navy-2);border-color:var(--navy-2);color:#fff}.action.primary:hover{background:var(--navy)}
.empty{padding:70px 24px;text-align:center;background:var(--paper);border:1px dashed var(--line);border-radius:14px;color:var(--ink-soft)}
@media(max-width:1000px){.filters{grid-template-columns:repeat(2,minmax(0,1fr))}.document-meta{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:900px){.shell{grid-template-columns:300px minmax(0,1fr)}.content{padding:28px 24px 70px}}
@media(max-width:700px){.shell{display:block}.sidebar{position:fixed;z-index:30;left:0;top:0;width:min(88vw,350px);transform:translateX(-105%);transition:transform .22s;box-shadow:20px 0 60px rgba(0,0,0,.18);overscroll-behavior:contain}body.sidebar-open .sidebar{transform:none}.mobile-toggle{display:inline-block}.topbar{padding:0 14px;height:58px}.breadcrumb{display:none}.content{padding:20px 14px 60px}.hero{padding:24px 20px}.hero h2{font-size:24px}.filters{grid-template-columns:1fr}.document-head{display:block}.status{margin-top:9px}.document-meta{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:430px){.document-meta{grid-template-columns:1fr}.page-link{font-size:10px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">跳到监管文件目录</a>
<div class="shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand"><h1>中国场外衍生品<br>法规知识库</h1></div>
    <div class="summary"><div><b id="document-count">—</b><span>法规数量</span></div><div><b id="authority-count">—</b><span>发文主体</span></div></div>
    <div class="sidebar-search"><input class="search" id="sidebar-search" name="sidebar-search" type="search" placeholder="搜索发文主体…" aria-label="搜索发文主体" autocomplete="off" spellcheck="false"></div>
    <nav class="authority-list" id="authority-list" aria-label="发文主体目录"></nav>
  </aside>
  <main class="main" id="main-content">
    <header class="topbar"><button class="mobile-toggle" id="mobile-toggle" aria-label="打开发文主体目录" aria-controls="sidebar" aria-expanded="false">目录</button><div class="breadcrumb">法规知识库 / 监管文件总目录</div><a class="page-link" href="chunk_review.html">Chunk 切分查看</a></header>
    <div class="content">
      <section class="hero">
        <p class="hero-kicker">REGULATORY CATALOG</p>
        <h2>监管文件总目录</h2>
        <p>按当前正式法规库生成，展示法规名称、文号、发文主体、日期、效力状态与权威来源。可直接打开官网原文、本地原件或对应的 Chunk 切分结果。</p>
        <div class="filters">
          <div class="field"><label for="query">关键词</label><input id="query" name="query" type="search" placeholder="例如：收益凭证、发文主体或文号…" autocomplete="off" spellcheck="false"></div>
          <div class="field"><label for="authority-filter">发文主体</label><select id="authority-filter" name="authority"><option value="">全部主体</option></select></div>
          <div class="field"><label for="status-filter">效力状态</label><select id="status-filter" name="status"><option value="">全部状态</option></select></div>
          <div class="field"><label for="format-filter">文件格式</label><select id="format-filter" name="format"><option value="">全部格式</option></select></div>
        </div>
      </section>
      <div class="result-bar"><h3>正式监管文件</h3><p id="result-count" role="status" aria-live="polite"></p></div>
      <div id="results"></div>
    </div>
  </main>
</div>
<script type="application/json" id="catalog-data">__CATALOG_DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('catalog-data').textContent);
const docs=DATA.documents;
const numberFormat=new Intl.NumberFormat('zh-CN');
const dateFormat=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric'});
const esc=value=>String(value??'').replace(/[&<>"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
const normalize=value=>String(value??'').toLowerCase().replace(/\s+/g,'');
const slug=value=>'authority-'+Array.from(value).map(char=>char.codePointAt(0).toString(16)).join('-');
const formatDate=value=>{if(!value)return '—';const date=new Date(value+'T00:00:00');return Number.isNaN(date.getTime())?value:dateFormat.format(date)};
const formatBytes=value=>{if(!value)return '—';const units=['B','KB','MB'];let amount=value,index=0;while(amount>=1024&&index<units.length-1){amount/=1024;index++}return `${new Intl.NumberFormat('zh-CN',{maximumFractionDigits:1}).format(amount)} ${units[index]}`};
const statusClass=value=>/尚未|待/.test(value)?'pending':(/有效/.test(value)?'':'unknown');
const params=new URLSearchParams(location.search);
const controls={q:document.getElementById('query'),authority:document.getElementById('authority-filter'),status:document.getElementById('status-filter'),format:document.getElementById('format-filter')};

function unique(field){return [...new Set(docs.map(doc=>doc[field]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'))}
function fillSelect(control,values){values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;control.appendChild(option)})}
function filterDocs(){const q=normalize(controls.q.value);return docs.filter(doc=>(!q||normalize([doc.document_title,doc.document_number,doc.issuing_authority,doc.version].join(' ')).includes(q))&&(!controls.authority.value||doc.issuing_authority===controls.authority.value)&&(!controls.status.value||doc.validity_status===controls.status.value)&&(!controls.format.value||doc.source_type===controls.format.value))}
function syncUrl(){const url=new URL(location.href);Object.entries(controls).forEach(([key,control])=>control.value?url.searchParams.set(key,control.value):url.searchParams.delete(key));history.replaceState(null,'',url)}
function setSidebar(open){document.body.classList.toggle('sidebar-open',open);document.getElementById('mobile-toggle').setAttribute('aria-expanded',String(open))}

function renderSidebar(){const query=normalize(document.getElementById('sidebar-search').value);const counts=new Map();docs.forEach(doc=>counts.set(doc.issuing_authority,(counts.get(doc.issuing_authority)||0)+1));const selected=controls.authority.value;const authorities=[...counts].filter(([authority])=>!query||normalize(authority).includes(query));document.getElementById('authority-list').innerHTML=authorities.map(([authority,count])=>`<a class="authority-link ${selected===authority?'active':''}" href="#${slug(authority)}" data-authority="${esc(authority)}"><span>${esc(authority)}</span><small>${numberFormat.format(count)} 份</small></a>`).join('')||'<div class="empty">没有匹配的发文主体</div>'}
function renderCard(doc,index){const official=doc.official_url?`<a class="action primary" href="${esc(doc.official_url)}" target="_blank" rel="noopener noreferrer">查看官方原文</a>`:'';const local=doc.local_href?`<a class="action" href="${esc(doc.local_href)}" target="_blank" rel="noopener">打开本地原件</a>`:'';return `<article class="document-card" id="${esc(doc.document_id)}" style="animation-delay:${Math.min(index*12,160)}ms"><div class="document-head"><div><h5 class="document-title">${esc(doc.document_title)}</h5><p class="document-number">${esc(doc.document_number||'文号未载')}</p></div><span class="status ${statusClass(doc.validity_status)}">${esc(doc.validity_status)}</span></div><dl class="document-meta"><div><dt>发文主体</dt><dd>${esc(doc.issuing_authority)}</dd></div><div><dt>发布日期</dt><dd>${formatDate(doc.publication_date)}</dd></div><div><dt>施行日期</dt><dd>${formatDate(doc.effective_date)}</dd></div><div><dt>格式 / 大小</dt><dd>${esc(doc.source_type)} / ${formatBytes(doc.file_size)}</dd></div><div><dt>Chunk 数量</dt><dd>${numberFormat.format(doc.chunk_count)} 个</dd></div></dl><div class="actions">${official}${local}<a class="action" href="chunk_review.html#${esc(doc.document_id)}">查看 Chunk 切分</a></div></article>`}
function render(){const filtered=filterDocs();const groups=new Map();filtered.forEach(doc=>{if(!groups.has(doc.issuing_authority))groups.set(doc.issuing_authority,[]);groups.get(doc.issuing_authority).push(doc)});let index=0;document.getElementById('results').innerHTML=[...groups].map(([authority,groupDocs])=>`<section class="group" id="${slug(authority)}"><div class="group-title"><h4>${esc(authority)}</h4><span>${numberFormat.format(groupDocs.length)} 份文件</span></div><div class="document-list">${groupDocs.map(doc=>renderCard(doc,index++)).join('')}</div></section>`).join('')||'<div class="empty">没有符合当前条件的监管文件。</div>';document.getElementById('result-count').textContent=`显示 ${numberFormat.format(filtered.length)} / ${numberFormat.format(docs.length)} 份`;renderSidebar();syncUrl()}

document.getElementById('document-count').textContent=numberFormat.format(DATA.summary.documents);
document.getElementById('authority-count').textContent=numberFormat.format(DATA.summary.authorities);
fillSelect(controls.authority,unique('issuing_authority'));fillSelect(controls.status,unique('validity_status'));fillSelect(controls.format,unique('source_type'));
Object.entries(controls).forEach(([key,control])=>{control.value=params.get(key)||'';control.addEventListener(control.tagName==='SELECT'?'change':'input',render)});
document.getElementById('sidebar-search').addEventListener('input',renderSidebar);
document.getElementById('authority-list').addEventListener('click',event=>{const link=event.target.closest('[data-authority]');if(!link)return;event.preventDefault();controls.authority.value=controls.authority.value===link.dataset.authority?'':link.dataset.authority;render();setSidebar(false);document.getElementById('results').scrollIntoView({block:'start'})});
document.getElementById('mobile-toggle').addEventListener('click',()=>setSidebar(!document.body.classList.contains('sidebar-open')));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setSidebar(false);if(event.key==='/'&&document.activeElement.tagName!=='INPUT'&&document.activeElement.tagName!=='SELECT'){event.preventDefault();controls.q.focus()}});
render();
</script>
</body>
</html>
'''


def main() -> None:
    data = public_data()
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = HTML.replace("__CATALOG_DATA__", serialized)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT_PATH.relative_to(ROOT)),
        "documents": data["summary"]["documents"],
        "authorities": data["summary"]["authorities"],
        "chunks": data["summary"]["chunks"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
