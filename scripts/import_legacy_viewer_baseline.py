#!/usr/bin/env python3
"""Extract the user-approved seven-dimension viewer shell and baseline mappings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "knowledge_base/templates/regulation_viewer_legacy_7d.html"
DEFAULT_BASELINE = ROOT / "data/metadata/viewer_legacy_7d_baseline.json"
DATA_RE = re.compile(
    r'(<script type="application/json" id="viewer-data">)(.*?)(</script>)',
    re.DOTALL,
)
CLASSIFICATION_FIELDS = (
    "authority_groups",
    "trading_venues",
    "underlying_business_types",
    "client_entity_types",
    "client_entity_groups",
    "funding_sources",
    "product_vehicles",
    "conduct_categories",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="导入用户确认的旧版七维筛选器与分类基线")
    parser.add_argument("source_html", type=Path)
    parser.add_argument("--template-output", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--baseline-output", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()

    source = args.source_html.read_text(encoding="utf-8")
    match = DATA_RE.search(source)
    if not match:
        raise RuntimeError("旧版HTML缺少viewer-data")
    payload = json.loads(match.group(2))
    documents = payload.get("documents", [])
    if len(documents) != 214:
        raise RuntimeError(f"预期旧版214部法规，实际{len(documents)}")

    template = (
        source[: match.start(2)]
        + "{{VIEWER_DATA_JSON}}"
        + source[match.end(2) :]
    )
    baseline_documents = []
    for order, document in enumerate(documents, start=1):
        baseline_documents.append({
            "legacy_order": order,
            "document_title": document["document_title"],
            "official_url": document.get("official_url", ""),
            **{
                field: document.get(field, [])
                for field in CLASSIFICATION_FIELDS
            },
            "classification_evidence": document.get("classification_evidence", []),
            "classification_summary": document.get("classification_summary", ""),
            "classification_basis_new": document.get("classification_basis_new", ""),
            "classification_review_status": document.get("classification_review_status", ""),
        })

    baseline = {
        "source_file_name": args.source_html.name,
        "source_summary": payload.get("summary", {}),
        "documents": baseline_documents,
    }
    args.template_output.parent.mkdir(parents=True, exist_ok=True)
    args.baseline_output.parent.mkdir(parents=True, exist_ok=True)
    args.template_output.write_text(template, encoding="utf-8")
    args.baseline_output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "template": str(args.template_output),
        "baseline": str(args.baseline_output),
        "documents": len(baseline_documents),
        "template_bytes": len(template.encode("utf-8")),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
