#!/usr/bin/env python3
"""H2 测试 schema 漂移防护（R15-22 收尾）。

问题：`java-backend/src/test/resources/schema-h2.sql` 为手维护（停在 V70），
真实 Flyway 迁移已到 V83——单测基座与真实 schema 之间存在静默漂移。

本脚本静态解析 V1..V<latest> 迁移链（CREATE TABLE / ALTER TABLE ADD|DROP|
RENAME COLUMN / RENAME TO）得到最终表-列集合，与 schema-h2.sql 对比：

- 漂移全部命中基线（scripts/h2_schema_drift_baseline.json）→ 通过；
- 出现基线之外的**新增漂移** → 报错退出 1（防止漂移继续扩大）；
- `--update-baseline` 重新生成基线（修复漂移后运行）。

用法：
    python scripts/check-h2-schema-drift.py                # 校验
    python scripts/check-h2-schema-drift.py --list         # 打印全部漂移
    python scripts/check-h2-schema-drift.py --update-baseline
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIGRATION_DIR = REPO / "java-backend/src/main/resources/db/migration"
H2_SCHEMA = REPO / "java-backend/src/test/resources/schema-h2.sql"
BASELINE = Path(__file__).resolve().parent / "h2_schema_drift_baseline.json"

SKIP_KEYWORDS = {"PRIMARY", "UNIQUE", "KEY", "INDEX", "CONSTRAINT", "FOREIGN",
                 "FULLTEXT", "SPATIAL", "CHECK", "EXCLUDE", "PERIOD"}


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def split_top_level(s: str) -> list[str]:
    """按括号深度 0 且不在字符串字面量内的逗号切分。"""
    parts, depth, start, quote = [], 0, 0, None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == "'" and i + 1 < len(s):
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]


def parse_create_columns(body: str) -> set[str]:
    cols: set[str] = set()
    for part in split_top_level(body):
        m = re.match(r"`([^`]+)`", part)
        if m:
            cols.add(m.group(1).lower())
            continue
        m = re.match(r"(\w+)", part)
        if not m:
            continue
        word = m.group(1)
        if word.upper() in SKIP_KEYWORDS:
            continue
        cols.add(word.lower())
    return cols


def apply_statement(schema: dict[str, set[str]], stmt: str) -> None:
    stmt = re.sub(r"\s+", " ", stmt.strip())

    m = re.search(r"CREATE TABLE (?:IF NOT EXISTS )?[`]?(\w+)[`]?\s*\(", stmt, re.I)
    if m:
        table = m.group(1).lower()
        body = stmt[m.end():].rsplit(")", 1)[0]
        schema.setdefault(table, set()).update(parse_create_columns(body))
        return

    m = re.search(r"ALTER TABLE (?:IF EXISTS )?[`]?(\w+)[`]?", stmt, re.I)
    if not m:
        return
    table = m.group(1).lower()
    rest = stmt[m.end():]

    m = re.search(r"RENAME (?:TO|AS) [`]?(\w+)[`]?", rest, re.I)
    if m and not re.search(r"RENAME COLUMN", rest, re.I):
        if table in schema:
            schema[m.group(1).lower()] = schema.pop(table)
        return

    for m in re.finditer(
            r"ADD (?:COLUMN )?(?:IF NOT EXISTS )?[`]?(\w+)[`]?", rest, re.I):
        word = m.group(1)
        # ADD UNIQUE/INDEX/KEY/CONSTRAINT/PRIMARY/FOREIGN/FULLTEXT/CHECK 皆非列
        if word.upper() in SKIP_KEYWORDS:
            continue
        schema.setdefault(table, set()).add(word.lower())

    for m in re.finditer(
            r"(?:DROP|DELETE) COLUMN (?:IF EXISTS )?[`]?(\w+)[`]?", rest, re.I):
        schema.get(table, set()).discard(m.group(1).lower())

    for m in re.finditer(r"RENAME COLUMN [`]?(\w+)[`]? TO [`]?(\w+)[`]", rest, re.I):
        cols = schema.get(table)
        if cols and m.group(1).lower() in cols:
            cols.discard(m.group(1).lower())
            cols.add(m.group(2).lower())


def migration_sort_key(p: Path) -> tuple[int, str]:
    m = re.match(r"V(\d+)(?:_(\d+))?__", p.name)
    return (int(m.group(1)), m.group(2) or "") if m else (10**9, p.name)


def parse_migrations() -> dict[str, set[str]]:
    schema: dict[str, set[str]] = {}
    files = sorted(MIGRATION_DIR.glob("V*.sql"), key=migration_sort_key)
    for f in files:
        for stmt in split_statements(strip_comments(f.read_text(encoding="utf-8"))):
            apply_statement(schema, stmt)
    return schema


def parse_h2() -> dict[str, set[str]]:
    schema: dict[str, set[str]] = {}
    for stmt in split_statements(strip_comments(H2_SCHEMA.read_text(encoding="utf-8"))):
        apply_statement(schema, stmt)
    return schema


def compute_drift() -> tuple[set[str], set[str], set[str]]:
    """返回 (漂移全集, 缺失表, 缺失列)。条目格式：'table.*' / 'table.column'。"""
    real, h2 = parse_migrations(), parse_h2()
    drift: set[str] = set()
    missing_tables, missing_cols = set(), set()
    for table, cols in sorted(real.items()):
        if table not in h2:
            drift.add(f"{table}.*")
            missing_tables.add(table)
            continue
        for col in sorted(cols - h2[table]):
            drift.add(f"{table}.{col}")
            missing_cols.add(f"{table}.{col}")
    return drift, missing_tables, missing_cols


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="打印全部漂移明细")
    parser.add_argument("--update-baseline", action="store_true", help="以当前漂移重建基线")
    args = parser.parse_args()

    if not MIGRATION_DIR.exists() or not H2_SCHEMA.exists():
        print("✗ 未找到迁移目录或 schema-h2.sql")
        return 2

    drift, missing_tables, missing_cols = compute_drift()

    if args.update_baseline:
        BASELINE.write_text(
            json.dumps({"allowed": sorted(drift)}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(f"[ok] 基线已更新：{len(drift)} 条 → {BASELINE.relative_to(REPO)}")
        return 0

    baseline: set[str] = set()
    if BASELINE.exists():
        baseline = set(json.loads(BASELINE.read_text(encoding="utf-8"))["allowed"])

    new_drift = drift - baseline
    print(f"[info] 迁移最终表-列 vs schema-h2.sql：漂移 {len(drift)} 条"
          f"（基线容忍 {len(drift & baseline)}，新增 {len(new_drift)}）")
    if args.list or new_drift:
        for entry in sorted(new_drift or drift):
            print(f"  - {entry}")
    if new_drift:
        print("✗ 存在基线之外的新增漂移——新迁移的表/列未同步进 schema-h2.sql，"
              "或需 --update-baseline 重新评估基线")
        return 1
    if drift:
        head = ", ".join(sorted(missing_tables)[:5]) or \
               ", ".join(sorted(missing_cols)[:5])
        print(f"[ok] 无新增漂移（历史漂移仍在基线内，示例：{head}…）")
    else:
        print("[ok] schema-h2.sql 与迁移链完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
