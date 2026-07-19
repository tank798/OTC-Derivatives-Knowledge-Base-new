from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


URL_RE = re.compile(r"https?://[^)\s]+")


def read_markdown_table(path: Path) -> dict[str, str]:
    links: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.startswith("|") or line.startswith("|---") or "法规名称" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2:
            raise ValueError(f"第{line_number}行不是两列表格：{line}")
        title, link_cell = cells
        match = URL_RE.search(link_cell)
        if not match:
            raise ValueError(f"第{line_number}行没有有效HTTP链接：{line}")
        if title in links:
            raise ValueError(f"法规名称重复：{title}")
        links[title] = match.group(0)
    if not links:
        raise ValueError("Markdown中没有读取到法规链接")
    return links


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="以Markdown核验表为准同步法规official_url")
    parser.add_argument("--source", type=Path, required=True, help="两列Markdown表格：法规名称、官网链接")
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("data/metadata/regulations.jsonl"),
        help="规范法规元数据JSONL",
    )
    parser.add_argument(
        "--expected-missing",
        type=int,
        default=None,
        help="预期不在Markdown中的现有法规数量；不一致时拒绝写入",
    )
    parser.add_argument("--check", action="store_true", help="只检查差异，不写入")
    args = parser.parse_args()

    links = read_markdown_table(args.source)
    rows = read_jsonl(args.metadata)
    by_title = {row["document_title"]: row for row in rows}
    if len(by_title) != len(rows):
        raise ValueError("元数据中存在重复法规标题")

    unknown = sorted(set(links) - set(by_title))
    missing = sorted(set(by_title) - set(links))
    if unknown:
        raise ValueError(f"Markdown存在未匹配法规：{unknown}")
    if args.expected_missing is not None and len(missing) != args.expected_missing:
        raise ValueError(
            f"未出现在Markdown中的法规为{len(missing)}份，与预期{args.expected_missing}份不一致：{missing}"
        )

    changed = []
    for title, url in links.items():
        row = by_title[title]
        old_url = row.get("official_url", "")
        if old_url != url:
            changed.append({"document_title": title, "old_url": old_url, "new_url": url})
            row["official_url"] = url

    if not args.check and changed:
        args.metadata.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "markdown_rows": len(links),
                "metadata_rows": len(rows),
                "matched": len(links),
                "changed": len(changed),
                "unchanged": len(links) - len(changed),
                "preserved_missing": missing,
                "check_only": args.check,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
