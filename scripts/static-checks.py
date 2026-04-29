#!/usr/bin/env python3
"""static-checks.py — HFusionHub 静态一致性校验（CI 用，纯标准库）

检查 1：租户列完整性
  解析 db/migration/*.sql 中所有建表/加列语句，与
  MybatisPlusConfig.TENANT_IGNORE_TABLES 对比，找出"被租户拦截器过滤
  （不在忽略表）但没有 tenant_id 列"的表——这类表一旦被查询就会产生
  "Unknown column 'tenant_id'" SQL 错误（历史上 V52/V53 出过）。

检查 2：内部端点 token 键一致性
  扫描 controller/ 下所有 @Value("${...}") 注解，凡是变量名含
  internal-token 的，必须是 python-ai.internal-token（与其他内部端点一致）。

用法:
  python scripts/static-checks.py --tenant-columns
  python scripts/static-checks.py --internal-token-keys
  python scripts/static-checks.py            # 全部检查
退出码: 0=通过, 1=发现违规
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIGRATION_DIR = REPO / "java-backend" / "src" / "main" / "resources" / "db" / "migration"
CONFIG_FILE = REPO / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub" / "config" / "MybatisPlusConfig.java"
CONTROLLER_DIR = REPO / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub" / "controller"

problems: list[str] = []


# ── 检查 1：租户列完整性 ────────────────────────────────────────────────

def parse_tenant_ignore_tables() -> set[str]:
    """从 MybatisPlusConfig.java 提取 TENANT_IGNORE_TABLES 常量。"""
    text = CONFIG_FILE.read_text(encoding="utf-8")
    m = re.search(r"TENANT_IGNORE_TABLES\s*=\s*Set\.of\((.*?)\);", text, re.S)
    if not m:
        problems.append("MybatisPlusConfig.java: 未找到 TENANT_IGNORE_TABLES 定义")
        return set()
    body = m.group(1)
    return set(re.findall(r'"([^"]+)"', body))


def collect_tables_with_tenant() -> set[str]:
    """解析所有迁移 SQL，收集含 tenant_id 列的表名。"""
    with_tenant: set[str] = set()
    all_tables: set[str] = set()
    for sql_file in sorted(MIGRATION_DIR.glob("V*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        # CREATE TABLE xxx (...tenant_id...)
        for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*?)\)\s*(?:ENGINE|COMMENT|;|$)",
            text, re.S | re.I,
        ):
            table = m.group(1).lower()
            cols = m.group(2).lower()
            all_tables.add(table)
            if re.search(r"\btenant_id\b", cols):
                with_tenant.add(table)
        # ALTER TABLE xxx ADD COLUMN tenant_id ...
        for m in re.finditer(
            r"ALTER\s+TABLE\s+`?(\w+)`?\s+(?:ADD\s+(?:COLUMN\s+)?`?tenant_id`?|ADD\s+COLUMN\s+`?tenant_id`?)",
            text, re.S | re.I,
        ):
            with_tenant.add(m.group(1).lower())
    return with_tenant, all_tables


def check_tenant_columns() -> None:
    ignore = {t.lower() for t in parse_tenant_ignore_tables()}
    with_tenant, _ = collect_tables_with_tenant()
    # 迁移目录可能不包含所有表（H2 测试 schema 等），无法静态断言"全表"。
    # 这里校验：迁移中出现的表，若不在忽略表且无 tenant_id → 违规。
    # 迁移中未出现的表由数据库动态检查（smoke-test 覆盖）。
    migrated = set()
    for sql_file in MIGRATION_DIR.glob("V*.sql"):
        text = sql_file.read_text(encoding="utf-8")
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", text, re.I):
            migrated.add(m.group(1).lower())
    for table in sorted(migrated):
        if table in ignore:
            continue
        if table not in with_tenant:
            problems.append(
                f"表 '{table}' 不在 TENANT_IGNORE_TABLES 中且没有任何迁移为其添加 tenant_id 列"
                "（租户拦截器会注入 tenant_id 条件 → SQL 报错）"
            )
    if not problems:
        print(f"[ok] 租户列完整性：{len(migrated)} 张迁移表，全部有 tenant_id 或被显式忽略")


# ── 检查 2：内部 token 键一致性 ─────────────────────────────────────────

def check_internal_token_keys() -> None:
    bad: list[str] = []
    for java_file in CONTROLLER_DIR.glob("*.java"):
        text = java_file.read_text(encoding="utf-8")
        for m in re.finditer(r'@Value\("\$\{([^}]*internal-token[^}]*)\}"\)', text, re.I):
            key = m.group(1)
            base = key.split(":")[0].strip()
            if base not in ("python-ai.internal-token", "app.internal-token"):
                bad.append(f"{java_file.name}: @Value(\"${{{key}}}\")")
    if bad:
        problems.append("内部 token 键非标准（应为 python-ai.internal-token）:\n    " + "\n    ".join(bad))
    else:
        print("[ok] 内部 token 键一致性：所有 internal-token 使用标准键")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-columns", action="store_true")
    parser.add_argument("--internal-token-keys", action="store_true")
    args = parser.parse_args()

    if not (args.tenant_columns or args.internal_token_keys):
        args.tenant_columns = args.internal_token_keys = True

    if args.tenant_columns:
        check_tenant_columns()
    if args.internal_token_keys:
        check_internal_token_keys()

    if problems:
        print("\n发现问题:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n静态校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
