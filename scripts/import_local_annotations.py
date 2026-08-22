#!/usr/bin/env python3
"""Extract Word/PDF annotations for the standalone regulation viewer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from lxml import etree
from pypdf import PdfReader

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional quote positioning helper
    pdfplumber = None


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
VIEWER_DATA_RE = re.compile(
    r'<script\s+type="application/json"\s+id="viewer-data">(.*?)</script>', re.DOTALL
)
SEED_RE = re.compile(
    r'(<script\s+type="application/json"\s+id="personal-workspace-seed">)(.*?)(</script>)',
    re.DOTALL,
)
SUPPORTED_SUFFIXES = {".doc", ".docx", ".pdf"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\.(?:doc|docx|pdf)$", "", value, flags=re.IGNORECASE)
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", value).lower()


def compact_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def stable_comment_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:18]
    return f"external-{digest}"


def iter_input_files(inputs: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for source in inputs:
        if source.is_file() and source.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(source.resolve())
        elif source.is_dir():
            files.extend(
                path.resolve()
                for path in source.rglob("*")
                if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
            )
    return sorted(set(files), key=lambda path: str(path).lower())


def load_catalog(html_path: Path) -> list[dict[str, Any]]:
    html = html_path.read_text(encoding="utf-8")
    match = VIEWER_DATA_RE.search(html)
    if not match:
        raise ValueError("HTML中未找到viewer-data")
    payload = json.loads(match.group(1))
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError("viewer-data.documents格式错误")
    return documents


def match_document(path: Path, documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    source = normalized_name(path.name)
    exact: list[dict[str, Any]] = []
    scored: list[tuple[float, dict[str, Any]]] = []
    for document in documents:
        candidates = {
            normalized_name(str(document.get("file_name") or "")),
            normalized_name(str(document.get("document_title") or "")),
        }
        candidates.discard("")
        if source in candidates:
            exact.append(document)
            continue
        score = max((SequenceMatcher(None, source, candidate).ratio() for candidate in candidates), default=0)
        scored.append((score, document))
    if len(exact) == 1:
        return exact[0]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 0.82 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.04):
        return scored[0][1]
    return None


def text_from_word_paragraph(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS)).strip()


def extract_docx_comments(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "word/comments.xml" not in names or "word/document.xml" not in names:
            return []
        if any(archive.getinfo(name).file_size > 50_000_000 for name in ("word/comments.xml", "word/document.xml")):
            raise ValueError("Word批注XML过大")
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
        comments_root = etree.fromstring(archive.read("word/comments.xml"), parser=parser)
        document_root = etree.fromstring(archive.read("word/document.xml"), parser=parser)

    comments: dict[str, dict[str, str]] = {}
    for element in comments_root.xpath("//w:comment", namespaces=NS):
        comment_id = element.get(f"{{{W_NS}}}id", "")
        paragraphs = [text_from_word_paragraph(item) for item in element.xpath("./w:p", namespaces=NS)]
        comments[comment_id] = {
            "note": "\n".join(item for item in paragraphs if item).strip(),
            "author": element.get(f"{{{W_NS}}}author", ""),
            "date": element.get(f"{{{W_NS}}}date", ""),
        }

    selected: dict[str, list[str]] = {comment_id: [] for comment_id in comments}
    active: list[str] = []
    for event, element in etree.iterwalk(document_root, events=("start", "end")):
        local_name = etree.QName(element).localname
        if event == "start" and local_name == "commentRangeStart":
            comment_id = element.get(f"{{{W_NS}}}id", "")
            if comment_id in comments and comment_id not in active:
                active.append(comment_id)
        elif event == "start" and local_name == "commentRangeEnd":
            comment_id = element.get(f"{{{W_NS}}}id", "")
            if comment_id in active:
                active.remove(comment_id)
        elif event == "end" and local_name == "t" and element.text:
            for comment_id in active:
                selected[comment_id].append(element.text)
        elif event == "end" and local_name == "p":
            for comment_id in active:
                selected[comment_id].append(" ")

    rows: list[dict[str, Any]] = []
    for index, (comment_id, metadata) in enumerate(comments.items(), start=1):
        quote = compact_text("".join(selected.get(comment_id, [])), 2000)
        note = compact_text(metadata["note"], 8000)
        if not quote and not note:
            continue
        rows.append(
            {
                "id": stable_comment_id(path.name, comment_id, quote, note),
                "quote": quote,
                "note": note or "批注",
                "author": compact_text(metadata["author"], 120),
                "source_file": path.name,
                "source_page": "",
                "created_at": metadata["date"] or now_iso(),
                "updated_at": now_iso(),
                "source_type": "DOCX",
                "source_index": index,
            }
        )
    return rows


def extract_legacy_doc_comments(path: Path) -> list[dict[str, Any]]:
    soffice = shutil.which("soffice") or ("/opt/homebrew/bin/soffice" if Path("/opt/homebrew/bin/soffice").exists() else "")
    if not soffice:
        raise RuntimeError("读取DOC批注需要LibreOffice")
    with tempfile.TemporaryDirectory(prefix="regulation-doc-comments-") as directory:
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", directory, str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        converted = Path(directory) / f"{path.stem}.docx"
        if result.returncode or not converted.exists():
            raise RuntimeError(compact_text(result.stderr or result.stdout or "DOC转换失败", 300))
        rows = extract_docx_comments(converted)
        for index, row in enumerate(rows, start=1):
            row["source_file"] = path.name
            row["id"] = stable_comment_id(path.name, index, row.get("quote"), row.get("note"))
        return rows


def annotation_rectangles(annotation: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    points = annotation.get("/QuadPoints")
    rectangles: list[tuple[float, float, float, float]] = []
    if points:
        values = [float(value) for value in points]
        for offset in range(0, len(values) - 7, 8):
            quad = values[offset : offset + 8]
            xs, ys = quad[0::2], quad[1::2]
            rectangles.append((min(xs), min(ys), max(xs), max(ys)))
    if not rectangles and annotation.get("/Rect"):
        rect = [float(value) for value in annotation["/Rect"]]
        if len(rect) >= 4:
            rectangles.append((min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])))
    return rectangles


def extract_pdf_quote(plumber_page: Any, rectangles: list[tuple[float, float, float, float]]) -> str:
    if plumber_page is None:
        return ""
    page_height = float(plumber_page.height)
    fragments: list[str] = []
    for x0, y0, x1, y1 in rectangles:
        top, bottom = max(0.0, page_height - y1 - 2), min(page_height, page_height - y0 + 2)
        left, right = max(0.0, x0 - 2), min(float(plumber_page.width), x1 + 2)
        if right <= left or bottom <= top:
            continue
        text = plumber_page.crop((left, top, right, bottom)).extract_text(x_tolerance=2, y_tolerance=2) or ""
        if text.strip():
            fragments.append(text)
    return compact_text(" ".join(fragments), 2000)


def extract_pdf_comments(path: Path) -> list[dict[str, Any]]:
    reader = PdfReader(str(path))
    plumber = pdfplumber.open(path) if pdfplumber else None
    labels = {
        "/Highlight": "高亮",
        "/Underline": "下划线",
        "/StrikeOut": "删除线",
        "/Squiggly": "波浪线",
        "/Ink": "画笔",
        "/FreeText": "文本批注",
        "/Text": "批注",
    }
    rows: list[dict[str, Any]] = []
    try:
        for page_index, page in enumerate(reader.pages):
            annotations = page.get("/Annots") or []
            plumber_page = plumber.pages[page_index] if plumber and page_index < len(plumber.pages) else None
            for annotation_index, reference in enumerate(annotations):
                annotation = reference.get_object()
                subtype = str(annotation.get("/Subtype") or "")
                if subtype not in labels:
                    continue
                rectangles = annotation_rectangles(annotation)
                quote = extract_pdf_quote(plumber_page, rectangles)
                raw_note = compact_text(annotation.get("/Contents") or "", 8000)
                note = raw_note or labels[subtype]
                rows.append(
                    {
                        "id": stable_comment_id(path.name, page_index, annotation_index, subtype, quote, note),
                        "quote": quote,
                        "note": note,
                        "author": compact_text(annotation.get("/T") or "", 120),
                        "source_file": path.name,
                        "source_page": str(page_index + 1),
                        "created_at": compact_text(annotation.get("/M") or "", 120) or now_iso(),
                        "updated_at": now_iso(),
                        "source_type": "PDF",
                        "annotation_type": labels[subtype],
                    }
                )
    finally:
        if plumber:
            plumber.close()
    return rows


def extract_annotations(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".docx":
        return extract_docx_comments(path)
    if path.suffix.lower() == ".doc":
        return extract_legacy_doc_comments(path)
    if path.suffix.lower() == ".pdf":
        return extract_pdf_comments(path)
    return []


def build_payload(files: list[Path], documents: list[dict[str, Any]]) -> dict[str, Any]:
    output_documents: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    file_results: list[dict[str, Any]] = []
    for path in files:
        document = match_document(path, documents)
        if not document:
            unmatched.append(path.name)
            file_results.append({"file": path.name, "status": "unmatched", "comments": 0})
            continue
        try:
            comments = extract_annotations(path)
        except Exception as error:
            file_results.append({"file": path.name, "status": "error", "comments": 0, "error": compact_text(error, 300)})
            continue
        document_id = str(document["document_id"])
        row = output_documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "document_title": document.get("document_title", ""),
                "comments": [],
                "drawings": [],
                "updated_at": now_iso(),
            },
        )
        existing = {comment["id"] for comment in row["comments"]}
        row["comments"].extend(comment for comment in comments if comment["id"] not in existing)
        file_results.append({"file": path.name, "status": "matched", "document_id": document_id, "comments": len(comments)})
    comment_count = sum(len(row["comments"]) for row in output_documents.values())
    return {
        "format": "场外衍生品法规知识库个人工作区",
        "version": 2,
        "seed_id": f"local-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hashlib.sha1(str(files).encode()).hexdigest()[:8]}",
        "exported_at": now_iso(),
        "favorites": [],
        "documents": output_documents,
        "note_count": comment_count,
        "files": file_results,
        "unmatched": unmatched,
    }


def write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def embed_payload(html_path: Path, payload: dict[str, Any]) -> Path:
    html = html_path.read_text(encoding="utf-8")
    match = SEED_RE.search(html)
    if not match:
        raise ValueError("HTML中未找到personal-workspace-seed")
    try:
        existing = json.loads(match.group(2))
    except json.JSONDecodeError:
        existing = {}
    existing_documents = existing.get("documents") if isinstance(existing.get("documents"), dict) else {}
    merged_documents = dict(existing_documents)
    for document_id, incoming in payload.get("documents", {}).items():
        current = merged_documents.get(document_id, {})
        comment_map = {item.get("id"): item for item in current.get("comments", []) if item.get("id")}
        comment_map.update({item.get("id"): item for item in incoming.get("comments", []) if item.get("id")})
        drawing_map = {item.get("id"): item for item in current.get("drawings", []) if item.get("id")}
        drawing_map.update({item.get("id"): item for item in incoming.get("drawings", []) if item.get("id")})
        merged_documents[document_id] = {
            **current,
            **incoming,
            "comments": list(comment_map.values()),
            "drawings": list(drawing_map.values()),
        }
    seed = {
        "version": 2,
        "seed_id": payload["seed_id"],
        "exported_at": payload["exported_at"],
        "favorites": sorted(set(existing.get("favorites", [])) | set(payload.get("favorites", []))),
        "documents": merged_documents,
    }
    serialized = json.dumps(seed, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    updated = SEED_RE.sub(lambda match: f"{match.group(1)}{serialized}{match.group(3)}", html, count=1)
    backup = html_path.with_name(f"{html_path.stem}.annotations-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{html_path.suffix}")
    shutil.copy2(html_path, backup)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=html_path.parent, delete=False) as handle:
        handle.write(updated)
        temporary_path = Path(handle.name)
    temporary_path.replace(html_path)
    return backup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="提取Word/PDF批注并生成知识库个人工作区数据")
    parser.add_argument("--input", nargs="+", required=True, type=Path, help="DOC/DOCX/PDF文件或目录")
    parser.add_argument("--html", required=True, type=Path, help="知识库HTML")
    parser.add_argument("--output", type=Path, default=Path("output/personal_annotations_import.json"), help="导入JSON")
    parser.add_argument("--embed", action="store_true", help="备份后把批注嵌入HTML")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_path = args.html.resolve()
    files = iter_input_files(args.input)
    if not files:
        print("未找到DOCX或PDF文件", file=sys.stderr)
        return 2
    documents = load_catalog(html_path)
    payload = build_payload(files, documents)
    write_json(payload, args.output.resolve())
    backup = embed_payload(html_path, payload) if args.embed else None
    summary = {
        "files": len(files),
        "matched": sum(1 for item in payload["files"] if item["status"] == "matched"),
        "unmatched": len(payload["unmatched"]),
        "errors": sum(1 for item in payload["files"] if item["status"] == "error"),
        "comments": payload["note_count"],
        "output": str(args.output.resolve()),
        "embedded": bool(args.embed),
        "backup": str(backup) if backup else "",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
