#!/usr/bin/env python
"""Build the frozen synthetic 工程施工 (construction) KB manifest (P2-4).

与 ``evaluation/kb_bid/build_kb_manifest.py`` 同构：每个 ``## [slug] Title``
章节是一个确定性 chunk，稳定 id 为 ``{doc_id}#{slug}``。输出提交入库，
作为 suite_bid_construction 冻结的 ground truth。

本语料为脱敏虚构招标文件（蓉城市政道路提升改造工程），仅用于评测与演示
种子，不包含任何真实企业数据。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KB_ROOT = Path(__file__).resolve().parent
DOCS_DIR = KB_ROOT / "docs"
MANIFEST_PATH = KB_ROOT / "kb_manifest.json"

SECTION_RE = re.compile(r"^##\s+\[([a-z0-9-]+)\]\s+(.+)$", re.MULTILINE)

KB_ID = 202
KB_VERSION = "1.0.0"
KB_NAME = "synthetic-bid-construction-kb"


def extract_documents() -> list[dict]:
    documents = []
    for filename in sorted(DOCS_DIR.glob("*.md")):
        text = filename.read_text(encoding="utf-8")
        title = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        sections = [
            {"section_id": slug, "title": title_text}
            for slug, title_text in SECTION_RE.findall(text)
        ]
        if not sections:
            raise SystemExit(f"{filename}: no `## [slug] Title` sections found")
        documents.append({
            "doc_id": filename.stem,
            "title": title,
            "filename": f"docs/{filename.name}",
            "sections": sections,
        })
    if not documents:
        raise SystemExit(f"no documents found under {DOCS_DIR}")
    return documents


def main() -> int:
    documents = extract_documents()
    manifest = {
        "kb_id": KB_ID,
        "version": KB_VERSION,
        "name": KB_NAME,
        "document_count": len(documents),
        "section_count": sum(len(doc["sections"]) for doc in documents),
        "documents": documents,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {MANIFEST_PATH}: {len(documents)} documents, "
          f"{manifest['section_count']} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
