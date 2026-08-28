#!/usr/bin/env python
"""纯检索 recall@5 归因探针（R16-1 残余差异归因工具）。

不经 LLM 答案层，直接对冻结套件逐用例检索并按 expected_document_names
计算 doc 级 recall@5，用于把 runtime 轨的检索指标变化拆分为：

1. **检索栈本身**（embedding / 通道 / RRF / ACL 过滤）——本探针的输出；
2. **答案层**（runtime 的 sources 从 /api/chat 响应提取，受模型行为、
   压缩、sources 附加策略影响）——runtime 基线与本探针的差值。

用法（仓库根目录，需 Python 服务依赖环境）::

    # 1. 生成 doc id → 标题映射（替换 <密码>）：
    #    docker exec mysql8 mysql --default-character-set=utf8mb4 \
    #      -uhfusionhub -p<密码> -e \
    #      "SELECT id,title FROM hfusionhub.document WHERE knowledge_base_id=101 AND deleted=0;" \
    #      > docmap.tsv   # 转 JSON: {"<id>": "<title>", ...}
    # 2. 跑探针：
    #    python python-ai/scripts/eval_retrieval_live.py \
    #      --cases python-ai/evaluation/suite/cases.jsonl \
    #      --docmap docmap.json

2026-09-09 首次归因结论（真机栈）：纯检索 OVERALL 0.830
（normal 0.986 / cross_document 0.983 / long_document 1.0 / tool 0.9 /
injection 0.84 / permission 0——ACL 正确拦截；permission 按 admin 老口径
= 1.0），证明检索栈与 2026-09-06 旧基线（0.856）同水平；runtime 答案层
0.550 与纯检索 0.830 的差值在答案层（与单任务 token 1582→774 同源的
模型侧行为漂移），与本仓代码改动无关。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.embedding import get_embedding_service  # noqa: E402
from app.core.security.clearance import (  # noqa: E402
    build_acl_metadata_filter,
    clear_clearance,
    set_clearance,
)
from app.core.tenant.context import set_tenant_id  # noqa: E402
from app.core.vectorstore.milvus_store import search_similar  # noqa: E402


def subject_for(category: str) -> str:
    """与 eval_runtime.subject_for_case 一致：permission 走最低权限主体。"""
    return "general" if category == "permission" else "admin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", required=True, help="冻结套件 cases.jsonl")
    parser.add_argument("--docmap", required=True, help='doc id → 标题 JSON：{"189": "标题", ...}')
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    cases = [json.loads(line) for line in open(args.cases, encoding="utf-8") if line.strip()]
    docmap = {int(k): v for k, v in json.load(open(args.docmap, encoding="utf-8")).items()}

    set_tenant_id(1)
    svc = get_embedding_service()

    def titles_of(rows: list[dict]) -> set[str]:
        out: set[str] = set()
        for r in rows:
            try:
                title = docmap.get(int(r.get("document_id")))
            except (TypeError, ValueError):
                title = None
            if title:
                out.add(title)
        return out

    stats: dict[str, dict] = defaultdict(lambda: {"sum": 0.0, "n": 0})
    admin_variant_perm = {"sum": 0.0, "n": 0}
    started = time.time()

    for i, case in enumerate(cases):
        expected = set(case["expected_document_names"])
        subject = subject_for(case["category"])
        set_clearance(subject)
        embedding = svc.get_query_embedding(case["query"])
        rows = search_similar(
            query_embedding=embedding,
            knowledge_base_id=case["kb_id"],
            top_k=args.top_k,
            metadata_filter=build_acl_metadata_filter(subject),
        )
        recall = (
            len(expected & titles_of(rows)) / max(1, len(expected)) if expected else 1.0
        )
        bucket = stats[case["category"]]
        bucket["sum"] += recall
        bucket["n"] += 1
        if case["category"] == "permission":
            # 老口径对照：permission 用例若按 admin 检索（ACL 前）的召回，
            # 用于量化「ACL 拒答不贡献检索召回」的口径变化幅度
            set_clearance("admin")
            rows_admin = search_similar(
                query_embedding=embedding,
                knowledge_base_id=case["kb_id"],
                top_k=args.top_k,
            )
            recall_admin = (
                len(expected & titles_of(rows_admin)) / max(1, len(expected))
                if expected
                else 1.0
            )
            admin_variant_perm["sum"] += recall_admin
            admin_variant_perm["n"] += 1
        if (i + 1) % 60 == 0:
            print(f"... {i + 1}/{len(cases)} ({time.time() - started:.0f}s)", flush=True)
    clear_clearance()

    print(f"\n=== 纯检索 recall@{args.top_k}（按各自主体权限，复刻 runtime 语义）===")
    total_sum = total_n = 0
    for category, bucket in sorted(stats.items()):
        print(f"{category:16s} {bucket['sum'] / bucket['n']:.3f}  (n={bucket['n']})")
        total_sum += bucket["sum"]
        total_n += bucket["n"]
    print(f"{'OVERALL':16s} {total_sum / total_n:.3f}  (n={total_n})")
    if admin_variant_perm["n"]:
        print(
            f"\npermission 按 admin 检索（老口径）: "
            f"{admin_variant_perm['sum'] / max(1, admin_variant_perm['n']):.3f} "
            f"(n={admin_variant_perm['n']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
