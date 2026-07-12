from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config
from models import Unit
from utils.text import stable_id

LOGGER = logging.getLogger("regulatory_chunker.semantic_llm")


def _read_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _request(payload: dict, api_key: str) -> str:
    request = Request(
        config.DEEPSEEK_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _parse_json(value: str) -> dict:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型未返回JSON对象")
    return json.loads(value[start:end + 1])


def review_boundaries(document_title: str, units: list[Unit], cache_path: Path) -> tuple[set[int], set[int], list[str]]:
    if not config.ENABLE_LLM_SEMANTIC_REVIEW or len(units) < 2:
        return set(), set(), []
    if not config.DEEPSEEK_API_KEY_FILE.exists():
        return set(), set(), ["DeepSeek API key文件不存在，已使用本地规则回退"]
    api_key = config.DEEPSEEK_API_KEY_FILE.read_text(encoding="utf-8").strip()
    if not api_key:
        return set(), set(), ["DeepSeek API key为空，已使用本地规则回退"]
    cache = _read_cache(cache_path)
    breaks: set[int] = set()
    overlaps: set[int] = set()
    warnings: list[str] = []
    for start in range(0, len(units), config.LLM_BATCH_UNITS):
        batch = units[start:start + config.LLM_BATCH_UNITS]
        if len(batch) < 2:
            continue
        digest = stable_id(document_title, config.DEEPSEEK_MODEL, *[unit.body_text for unit in batch])
        cached = cache.get(digest)
        if cached is None:
            compact_units = [
                {
                    "index": start + offset,
                    "type": unit.kind,
                    "article": unit.article_start,
                    "chapter": unit.hierarchy.get("chapter_title", ""),
                    "section": unit.hierarchy.get("section_title", ""),
                    "text": unit.body_text[:260],
                }
                for offset, unit in enumerate(batch)
            ]
            system = (
                "你是中国金融监管法规文档切分审核器。只判断相邻完整结构单元的语义边界，不改写原文。"
                "break_before列出应在该index之前换块的索引；overlap_before列出因前条、前款、例外、定义依赖而建议在该index前重叠上一完整单元的索引。"
                "新章新节、监管主题明显变化应换块。连续定义、原则与例外尽量保持连续。"
                "仅返回JSON：{\"break_before\":[],\"overlap_before\":[],\"reason\":\"\"}。"
            )
            payload = {
                "model": config.DEEPSEEK_MODEL,
                "temperature": 0,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps({"document_title": document_title, "units": compact_units}, ensure_ascii=False)},
                ],
            }
            for attempt in range(3):
                try:
                    cached = _parse_json(_request(payload, api_key))
                    cache[digest] = cached
                    _write_cache(cache_path, cache)
                    break
                except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    if attempt == 2:
                        warnings.append(f"DeepSeek语义复核失败，本批使用本地规则：{type(exc).__name__}")
                    else:
                        time.sleep(2 ** attempt)
            if cached is None:
                continue
        valid = set(range(start + 1, start + len(batch)))
        breaks.update(int(value) for value in cached.get("break_before", []) if isinstance(value, int) and value in valid)
        overlaps.update(int(value) for value in cached.get("overlap_before", []) if isinstance(value, int) and value in valid)
    return breaks, overlaps, warnings
