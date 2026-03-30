#!/usr/bin/env python
"""Build the frozen synthetic-KB manifest from the committed Markdown docs.

Each section header ``## [slug] Title`` defines one deterministic chunk whose
stable id is ``{doc_id}#{slug}``.  The output is committed and treated as the
frozen ground truth for the evaluation suite.

The output is fully deterministic: documents are ordered by filename and no
timestamps are written.
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

KB_ID = 101
KB_VERSION = "1.0.0"
KB_NAME = "synthetic-business-kb"


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
