#!/usr/bin/env python
"""一次性播种脚本：把合成评测 KB 的 10 篇文档上传到 kb 101 并索引。

标题取自 ``python-ai/evaluation/kb/kb_manifest.json``（套件用例按这些中文
标题断言，文件名做标题会导致 runtime 评测全部对不上号）。重复执行先
purge 旧文档（连带清理 Milvus 向量）再上传。

用法：python scripts/seed_eval_kb.py   （在仓库根目录）
前提：Java(8080)/Python(9000) 已启动，docker/.env 含 ADMIN_PASSWORD；
     knowledge_base 101 已存在。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "python-ai" / "evaluation" / "kb"
DOCS = KB_DIR / "docs"
KB_ID = 101


def env_val(key: str) -> str:
    for line in (ROOT / "docker" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"docker/.env missing {key}")


def main() -> int:
    admin_pw = env_val("ADMIN_PASSWORD")
    java = "http://localhost:8080"

    login = httpx.post(f"{java}/api/user/login",
                       json={"username": "admin", "password": admin_pw}, timeout=30)
    login.raise_for_status()
    headers = {"satoken": login.json()["data"]}
    print("login ok")

    # ── 清理 KB 101 既有文档（purge 连带清理向量）──
    listing = httpx.get(f"{java}/api/document/list/{KB_ID}",
                        params={"page": 1, "pageSize": 100},
                        headers=headers, timeout=30)
    rows = []
    if listing.status_code == 200:
        data = listing.json().get("data") or {}
        rows = data.get("records") or data.get("list") or data.get("items") or []
    for row in rows:
        doc_id = row.get("id")
        purge = httpx.delete(f"{java}/api/document/{doc_id}/purge", headers=headers, timeout=60)
        print(f"purged old doc {doc_id} ({row.get('title')}) -> {purge.status_code}")
    if rows:
        time.sleep(3)  # 等向量清理落定

    # ── 按 manifest 的中文标题上传并索引 ──
    manifest = json.loads((KB_DIR / "kb_manifest.json").read_text(encoding="utf-8"))
    title_by_file = {Path(doc["filename"]).name: doc["title"]
                     for doc in manifest["documents"]}

    for md in sorted(DOCS.glob("*.md")):
        title = title_by_file.get(md.name, md.stem)
        up = httpx.post(
            f"{java}/api/document/upload",
            data={"title": title, "knowledgeBaseId": str(KB_ID)},
            files={"file": (md.name, md.read_bytes(), "text/markdown")},
            headers=headers, timeout=120,
        )
        try:
            up.raise_for_status()
            doc_id = up.json()["data"]["id"]
        except Exception as exc:
            print(f"[FAIL] upload {title}: {exc} {up.text[:200]}")
            return 1
        print(f"uploaded {title} -> doc {doc_id}")

        parse = httpx.post(f"{java}/api/document/{doc_id}/parse", headers=headers, timeout=30)
        if parse.status_code != 200:
            print(f"  [FAIL] parse trigger: {parse.text[:200]}")
            return 1

        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(3)
            doc = httpx.get(f"{java}/api/document/{doc_id}", headers=headers, timeout=30).json()
            status = doc.get("data", {}).get("status")
            if status == 2:
                print("  indexed ok")
                break
            if status == 3:
                print("  [FAIL] parse failed")
                return 1
        else:
            print("  [TIMEOUT] indexing not finished in 180s")
            return 1
    print("ALL SEEDED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
