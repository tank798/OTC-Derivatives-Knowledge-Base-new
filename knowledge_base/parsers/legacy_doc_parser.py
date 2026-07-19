from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import re
import uuid

from models import ParsedDocument
from parsers.docx_parser import parse_docx, strip_word_toc
from utils.metadata import infer_metadata
from utils.text import clean_text, compact, is_page_number, is_toc_field, strip_repeated_front_structure
from models import SourceBlock


def _blocks_from_plain_text(text: str) -> tuple[list[SourceBlock], list[str]]:
    text = re.sub(r"\b(?:HYPERLINK|PAGEREF|REF)\s+(?:\"[^\"]*\"|\S+)(?:\s+\\[a-z]+)*", "", text, flags=re.I)
    text = re.sub(r"\b(?:PAGE|NUMPAGES)\s+\\\*\s+MERGEFORMAT\s*\d*", "", text, flags=re.I)
    text = re.sub(r"(?m)^\s*PAGE\s*$", "", text, flags=re.I)
    paragraphs = [clean_text(value) for value in text.splitlines() if clean_text(value)]
    paragraphs = [value for value in paragraphs if not is_page_number(value) and not is_toc_field(value)]
    removed_toc = 0
    toc_marker = next((index for index, value in enumerate(paragraphs[:30]) if compact(value) in {"目录", "目次"}), None)
    if toc_marker is not None:
        # 旧 DOC 的目录与正文之间可能有签约前言。目录条目通常以页码
        # 结尾，因此只删除目录标题和连续目录条目，不能把第一个正文
        # “第X条”之前的全部内容一并裁掉。
        toc_end = toc_marker
        def toc_key(value: str) -> str:
            return re.sub(r"\s+\d{1,4}\s*$", "", re.sub(r"\s+", " ", clean_text(value))).strip()

        guide_prefix = paragraphs[toc_marker + 1:min(toc_marker + 130, len(paragraphs))]
        page_suffixed = sum(
            bool(re.search(r"\s+\d{1,4}\s*$", value))
            and bool(re.match(r"^(?:第.+[章节]|[一二三四五六七八九十百]+[、.]|附件|附录|说明及声明)", value))
            for value in guide_prefix
        )
        if guide_prefix and page_suffixed >= 3:
            first_key = toc_key(guide_prefix[0])
            duplicate = next(
                (
                    index for index in range(toc_marker + 2, len(paragraphs))
                    if toc_key(paragraphs[index]) == first_key
                    and not re.search(r"\s+\d{1,4}\s*$", paragraphs[index])
                ),
                None,
            )
            if duplicate is not None:
                removed_toc = duplicate - toc_marker
                paragraphs = paragraphs[:toc_marker] + paragraphs[duplicate:]
                toc_marker = None
        if toc_marker is None:
            pass
        else:
            for index in range(toc_marker + 1, min(len(paragraphs), toc_marker + 80)):
                value = paragraphs[index]
                article_toc = bool(
                    re.match(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条", value)
                    and re.search(r"\s\d{1,4}\s*$", value)
                )
                dotted_toc = bool(re.search(r"(?:\.{2,}|[…·]{2,})\s*\d{1,4}\s*$", value))
                if article_toc or dotted_toc or is_toc_field(value):
                    toc_end = index
                    continue
                if toc_end > toc_marker:
                    break
            if toc_end > toc_marker:
                removed_toc = toc_end - toc_marker + 1
                paragraphs = paragraphs[:toc_marker] + paragraphs[toc_end + 1:]
    blocks = [SourceBlock(value, block_id=f"b{index:05d}") for index, value in enumerate(paragraphs, start=1)]
    blocks, removed_front_structure = strip_repeated_front_structure(blocks)
    warnings: list[str] = []
    if removed_toc:
        warnings.append(f"已过滤{removed_toc}个旧DOC目录段落")
    if removed_front_structure:
        warnings.append(f"已过滤{removed_front_structure}个旧DOC前置目录标题")
    return blocks, warnings


def _extract_with_soffice(path: Path, soffice: str, temp_dir: str) -> str:
    profile = Path(temp_dir) / f"profile-{uuid.uuid4().hex}"
    command = [
        soffice,
        f"-env:UserInstallation={profile.as_uri()}",
        "--headless", "--convert-to", "txt:Text", "--outdir", temp_dir, str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    converted = Path(temp_dir) / (path.stem + ".txt")
    if completed.returncode != 0 or not converted.exists():
        return ""
    return converted.read_text(encoding="utf-8-sig", errors="replace")


def parse_legacy_doc(path: Path) -> ParsedDocument:
    soffice = shutil.which("soffice") or "/opt/homebrew/bin/soffice"
    with tempfile.TemporaryDirectory(prefix="regulatory_doc_") as temp_dir:
        # Direct text export preserves text boxes and other legacy Word objects
        # that can disappear when an old .doc is first converted to .docx.
        text = _extract_with_soffice(path, soffice, temp_dir)
        if text:
            blocks, cleanup_warnings = _blocks_from_plain_text(text)
            if blocks:
                return ParsedDocument(
                    path,
                    "doc",
                    blocks,
                    infer_metadata(blocks, path),
                    ["旧DOC经LibreOffice直接只读导出文本，原文件未修改", *cleanup_warnings],
                )
        command = [soffice, "--headless", "--convert-to", "docx", "--outdir", temp_dir, str(path)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        converted = Path(temp_dir) / (path.stem + ".docx")
        if completed.returncode == 0 and converted.exists():
            parsed = parse_docx(converted)
            parsed.file_path = path
            parsed.source_type = "doc"
            parsed.metadata = infer_metadata(parsed.blocks, path)
            parsed.warnings.append("旧DOC在临时目录经LibreOffice转换为DOCX后解析，原文件未修改")
            if parsed.blocks:
                return parsed
    textutil = shutil.which("textutil")
    if textutil:
        completed = subprocess.run([textutil, "-convert", "txt", "-stdout", str(path)], capture_output=True, timeout=120)
        if completed.returncode == 0 and completed.stdout:
            text = completed.stdout.decode("utf-8", errors="replace")
            blocks, cleanup_warnings = _blocks_from_plain_text(text)
            if blocks:
                warnings = ["LibreOffice转换失败，旧DOC通过macOS textutil只读抽取并清理域代码，原文件未修改", *cleanup_warnings]
                return ParsedDocument(path, "doc", blocks, infer_metadata(blocks, path), warnings)
    return ParsedDocument(path, "doc", [], {}, ["旧DOC的LibreOffice转换和textutil抽取均失败"], "failed")
