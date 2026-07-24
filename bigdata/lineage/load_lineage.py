#!/usr/bin/env python3
"""HFusionData Analytics — 表级血缘加载 + Mermaid 渲染。

读取 lineage.yaml 注册表:
  1. 写入 MySQL table_lineage(V83,由 Flyway 建表);
  2. 渲染 Mermaid flowchart 到 lineage.md(文档/演示用)。

用法(宿主机,需 pymysql):
  MYSQL_PASSWORD=<密码> python load_lineage.py [--skip-db]
"""

from __future__ import annotations

import argparse
import io
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "lineage.yaml")
MERMAID_OUT = os.path.join(HERE, "lineage.md")


def load_registry() -> dict:
    with io.open(REGISTRY, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_to_mysql(edges: list, mysql_password: str) -> int:
    import pymysql

    conn = pymysql.connect(host="127.0.0.1", port=3306, user="hfusionhub",
                           password=mysql_password, database="hfusionhub",
                           charset="utf8mb4")
    cur = conn.cursor()
    written = 0
    try:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        cur.execute("TRUNCATE TABLE table_lineage")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        for edge in edges:
            for src in edge["inputs"]:
                for tgt in edge["outputs"]:
                    cur.execute(
                        "INSERT INTO table_lineage (tenant_id, job_name, layer, "
                        "source_table, target_table) VALUES (-1, %s, %s, %s, %s)",
                        (edge["job"], edge["layer"], src, tgt))
                    written += 1
        conn.commit()
    finally:
        conn.close()
    return written


def render_mermaid(edges: list) -> str:
    lines = ["```mermaid", "flowchart LR"]
    node_ids = {}

    def node_id(table: str) -> str:
        if table not in node_ids:
            node_ids[table] = f"n{len(node_ids) + 1}"
            store = table.split(":", 1)
            label = f"{store[0]}·{store[1]}" if len(store) > 1 else table
            lines.append(f'    {node_ids[table]}["{label}"]')
        return node_ids[table]

    for edge in edges:
        jid = f'j{abs(hash(edge["job"])) % 10000}'
        lines.append(f'    {jid}{{"{edge["job"]}"}}')
        for src in edge["inputs"]:
            lines.append(f"    {node_id(src)} --> {jid}")
        for tgt in edge["outputs"]:
            lines.append(f"    {jid} --> {node_id(tgt)}")
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load table lineage + render Mermaid")
    parser.add_argument("--skip-db", action="store_true", help="仅渲染 Mermaid")
    args = parser.parse_args()

    registry = load_registry()
    edges = registry["edges"]

    mysql_password = os.environ.get("MYSQL_PASSWORD", "")
    if not args.skip_db:
        if not mysql_password:
            print("MYSQL_PASSWORD 未设置(或使用 --skip-db)")
            return 1
        written = load_to_mysql(edges, mysql_password)
        print(f"[lineage] MySQL table_lineage 写入 {written} 条血缘边")

    mermaid = render_mermaid(edges)
    with io.open(MERMAID_OUT, "w", encoding="utf-8", newline="\n") as f:
        header = ("# HFusionData Analytics — 表级血缘图\n\n"
                  f"由 load_lineage.py 从 lineage.yaml 渲染({len(edges)} 个作业节点)。\n\n")
        f.write(header + mermaid + "\n")
    print(f"[lineage] Mermaid 已渲染 → {MERMAID_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
