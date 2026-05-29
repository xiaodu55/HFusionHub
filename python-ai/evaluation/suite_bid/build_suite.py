#!/usr/bin/env python
"""Validate the 招投标 suite definitions and emit frozen ``cases.jsonl`` +
``suite_manifest.json`` (B2 垂直化)。

与 ``evaluation/suite/build_suite.py`` 同构，针对 ``evaluation/kb_bid``。
域规模较小（单领域），MIN_TOTAL_CASES 相应下调。``bid_facts`` 字段透传
写入 cases.jsonl，供离线评测做领域指标子串匹配。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parent
KB_ROOT = SUITE_DIR.parent / "kb_bid"
MANIFEST_PATH = KB_ROOT / "kb_manifest.json"
CASES_PATH = SUITE_DIR / "cases.jsonl"
SUITE_MANIFEST_PATH = SUITE_DIR / "suite_manifest.json"

SUITE_VERSION = "1.0.0"
CATEGORIES = {
    "normal": "普通问答（招标领域）",
}
VALID_RISKS = {"permission", "injection", "confidentiality"}
MIN_TOTAL_CASES = 20
MIN_CATEGORY_CASES = 10

# 允许透传的领域指标键（防 typo 漂移）
BID_METRIC_KEYS = {
    "qualification_recall",
    "disqualification_clause_recall",
    "scoring_point_accuracy",
    "bid_terminology_accuracy",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(definitions, manifest: dict) -> tuple[list[dict], dict[str, int]]:
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

        # bid_facts 透传校验
        bid_facts = case.get("bid_facts")
        if bid_facts is not None:
            if not isinstance(bid_facts, dict):
                errors.append(f"{case_id}: bid_facts must be a dict")
            else:
                for metric_key, facts in bid_facts.items():
                    if metric_key not in BID_METRIC_KEYS:
                        errors.append(f"{case_id}: unknown bid metric {metric_key!r}")
                    if not isinstance(facts, list) or not facts:
                        errors.append(f"{case_id}: bid metric {metric_key!r} must be a non-empty list")
                    elif not all(isinstance(f, str) and f.strip() for f in facts):
                        errors.append(f"{case_id}: bid metric {metric_key!r} facts must be non-empty strings")

        expected = list(case["expected_chunk_ids"])
        expected_names = list(case["expected_document_names"])
        derived_names: list[str] = []
        for chunk in expected:
            if ":" in chunk and "#" not in chunk:
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
    for category, minimum in (("normal", MIN_CATEGORY_CASES),):
        if counts[category] < minimum:
            errors.append(
                f"category {category!r} has {counts[category]} cases, need at least {minimum}"
            )

    if errors:
        raise SystemExit("\n".join(errors))
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
