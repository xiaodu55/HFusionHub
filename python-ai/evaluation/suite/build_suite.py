#!/usr/bin/env python
"""Validate the suite definitions against the KB manifest and emit the frozen
``cases.jsonl`` plus ``suite_manifest.json``.

The emitted ``cases.jsonl`` is committed and is the artifact consumed by both
the offline and runtime evaluators.  ``suite_manifest.json`` pins the suite
version, the KB version it was frozen against, a SHA-256 of the cases file, and
per-category counts so any drift is immediately visible in review.

Deterministic output: cases are sorted by id and no timestamps are written.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parent
KB_ROOT = SUITE_DIR.parent / "kb"
MANIFEST_PATH = KB_ROOT / "kb_manifest.json"
CASES_PATH = SUITE_DIR / "cases.jsonl"
SUITE_MANIFEST_PATH = SUITE_DIR / "suite_manifest.json"

SUITE_VERSION = "1.0.0"
CATEGORIES = {
    "normal": "普通问答",
    "cross_document": "跨文档问答",
    "refusal": "无答案拒答",
    "permission": "权限隔离",
    "injection": "提示注入",
    "tool": "工具调用",
    "long_document": "长文档检索",
}
VALID_RISKS = {"permission", "injection", "confidentiality"}
MIN_TOTAL_CASES = 200
MIN_CATEGORY_CASES = 15


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(definitions, manifest: dict) -> list[dict]:
    kb_id = int(manifest["kb_id"])
    sections = {
        (doc["doc_id"], section["section_id"])
        for doc in manifest["documents"]
        for section in doc["sections"]
    }
    manifest_titles = {doc["doc_id"]: doc["title"] for doc in manifest["documents"]}

    errors: list[str] = []
    cases: list[dict] = []
    seen_ids: set[str] = set()

    if definitions.DOC_TITLES != manifest_titles:
        errors.append(
            "suite_definitions.DOC_TITLES does not match kb_manifest.json: "
            f"docs={sorted(manifest_titles)}"
        )

    for case in definitions.ALL_CASES:
        case_id = str(case["id"])
        if case_id in seen_ids:
            errors.append(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        if case["category"] not in CATEGORIES:
            errors.append(f"{case_id}: unknown category {case['category']!r}")
        if int(case["kb_id"]) != kb_id:
            errors.append(f"{case_id}: kb_id mismatch (expected {kb_id})")
        if case["refusal"] not in ("none", "required"):
            errors.append(f"{case_id}: invalid refusal value {case['refusal']!r}")
        for risk in case["risk_labels"]:
            if risk not in VALID_RISKS:
                errors.append(f"{case_id}: invalid risk label {risk!r}")

        expected = list(case["expected_chunk_ids"])
        expected_names = list(case["expected_document_names"])
        derived_names: list[str] = []
        for chunk in expected:
            if ":" in chunk and "#" not in chunk:
                # refuse to be fooled by Windows path separators
                errors.append(f"{case_id}: chunk id {chunk!r} looks like a path")
                continue
            doc_id, _, section_id = chunk.partition("#")
            if (doc_id, section_id) not in sections:
                errors.append(f"{case_id}: unknown chunk reference {chunk!r}")
                continue
            title = manifest_titles[doc_id]
            if title not in derived_names:
                derived_names.append(title)
        if derived_names != expected_names:
            errors.append(
                f"{case_id}: expected_document_names {expected_names} != derived {derived_names}"
            )

        for fact in case["key_facts"]:
            if not isinstance(fact, str) or not fact.strip():
                errors.append(f"{case_id}: empty key fact")

        cases.append(case)

    counts = {category: 0 for category in CATEGORIES}
    for case in cases:
        counts[case["category"]] += 1

    if len(cases) < MIN_TOTAL_CASES:
        errors.append(
            f"suite has {len(cases)} cases, need at least {MIN_TOTAL_CASES}"
        )
    for category, minimum in (("normal", MIN_CATEGORY_CASES), ("long_document", 1)):
        if counts[category] < minimum:
            errors.append(
                f"category {category!r} has {counts[category]} cases, need at least {minimum}"
            )

    return cases, counts


def emit_cases(cases: list[dict], path: Path) -> None:
    ordered = sorted(cases, key=lambda case: case["id"])
    path.write_text(
        "\n".join(
            json.dumps(case, ensure_ascii=False, sort_keys=True)
            for case in ordered
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    definitions = load_module("suite_definitions", SUITE_DIR / "suite_definitions.py")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    cases, counts = validate(definitions, manifest)
    if cases and not counts:
        pass
    case_list = sorted(cases, key=lambda case: case["id"])
    emit_cases(case_list, CASES_PATH)

    cases_digest = hashlib.sha256(CASES_PATH.read_bytes()).hexdigest()
    suite_manifest = {
        "suite_version": SUITE_VERSION,
        "kb_id": int(manifest["kb_id"]),
        "kb_version": manifest["version"],
        "kb_name": manifest["name"],
        "total_cases": len(case_list),
        "category_counts": counts,
        "cases_sha256": cases_digest,
    }
    SUITE_MANIFEST_PATH.write_text(
        json.dumps(suite_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"wrote {CASES_PATH}: {len(case_list)} cases "
        f"(sha256={cases_digest[:12]}), {SUITE_MANIFEST_PATH.name}"
    )
    for category, count in counts.items():
        print(f"  {category:<15} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
