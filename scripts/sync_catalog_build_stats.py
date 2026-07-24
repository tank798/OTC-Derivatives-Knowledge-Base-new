from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "metadata" / "regulations.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "build_manifest.json"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="将正式构建统计同步回法规权威目录")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    catalog = load_jsonl(args.catalog)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    built_by_name = {
        str(record["file_name"]): record
        for record in manifest.get("documents", {}).values()
    }
    active_names = {
        str(record.get("file_name", ""))
        for record in catalog
        if not str(record.get("source_status", "")).startswith("excluded_")
    }
    missing = sorted(active_names - set(built_by_name))
    unexpected = sorted(set(built_by_name) - active_names)
    if missing or unexpected:
        raise RuntimeError(
            f"目录与构建清单不一致：missing={missing[:10]} unexpected={unexpected[:10]}"
        )

    updated = 0
    total_chunks = 0
    for record in catalog:
        if str(record.get("source_status", "")).startswith("excluded_"):
            record["chunk_count"] = 0
            record["character_count"] = 0
            continue
        built = built_by_name[str(record["file_name"])]
        summary = built.get("summary", {})
        record["document_id"] = built["document_id"]
        record["chunk_count"] = int(summary.get("chunk_count", len(built.get("chunk_ids", []))))
        record["character_count"] = int(summary.get("source_character_count", 0))
        record["clean_text_hash"] = built.get("clean_text_hash", "")
        record["structured_schema_version"] = built.get("structured_schema_version", "")
        record["cleaning_rule_version"] = built.get("cleaning_rule_version", "")
        record["parser_version"] = built.get("parser_version", "")
        record["chunker_version"] = built.get("chunker_version", "")
        record["processed_status"] = summary.get("status", "")
        total_chunks += record["chunk_count"]
        updated += 1

    if updated != int(manifest.get("document_count", -1)):
        raise RuntimeError(
            f"同步数量异常：updated={updated} manifest={manifest.get('document_count')}"
        )
    if total_chunks != int(manifest.get("chunk_count", -1)):
        raise RuntimeError(
            f"Chunk总数异常：catalog={total_chunks} manifest={manifest.get('chunk_count')}"
        )

    args.catalog.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in catalog) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "catalog_records": len(catalog),
        "active_documents": updated,
        "excluded_documents": len(catalog) - updated,
        "chunk_count": total_chunks,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
