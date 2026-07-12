from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceBlock:
    text: str
    style: str = ""
    source_kind: str = "paragraph"
    page: int = 0
    block_id: str = ""


@dataclass
class ParsedDocument:
    file_path: Path
    source_type: str
    blocks: list[SourceBlock]
    metadata: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    extraction_status: str = "success"


@dataclass
class Node:
    kind: str
    title: str = ""
    own_text: str = ""
    block_ids: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = field(default=None, repr=False)

    def add_child(self, node: "Node") -> None:
        node.parent = self
        self.children.append(node)


@dataclass
class Unit:
    body_text: str
    kind: str
    hierarchy: dict[str, str]
    article_start: str = ""
    article_end: str = ""
    paragraph_range: str = ""
    attachment_name: str = ""
    block_ids: list[str] = field(default_factory=list)
    is_oversized: bool = False
    oversized_reason: str = ""
    sequence_index: int = -1


@dataclass
class ChunkDraft:
    units: list[Unit]
    hierarchy: dict[str, str]
    is_overlapping: bool = False
    overlap_source_index: int | None = None
    is_oversized: bool = False
    oversized_reason: str = ""
    context_only_prefix: str = ""


@dataclass
class FileResult:
    document: ParsedDocument
    chunks: list[dict[str, Any]]
    validation: dict[str, Any]
