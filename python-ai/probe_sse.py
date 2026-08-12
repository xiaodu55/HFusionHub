#!/usr/bin/env python
"""B2 收尾探测：SSE 流式对话的分段耗时（Java 转发 vs Python 直连）。

对同一问题分别经两条链路发起流式请求，逐块读取 SSE，测量：
- TTFB：从发起到第一个携带 content 的事件（首包延迟 ≈ 意图分类 + 检索 + LLM 首包）
- TTL ：从发起到 [DONE]（完整生成）
- Java 转发开销 ≈ TTFB(java) - TTFB(python 直连)

用法：python scripts/../probe_sse.py（在 python-ai 目录）
"""
from __future__ import annotations

import json
import time

import httpx

JAVA = "http://localhost:8080/api"
PY = "http://localhost:9000/api"

admin = [l.split("=", 1)[1].strip() for l in open("../docker/.env", encoding="utf-8")
         if l.startswith("ADMIN_PASSWORD=")][0]
py_token = [l.split("=", 1)[1].strip() for l in open(".env", encoding="utf-8")
            if l.startswith("PYTHON_AI_INTERNAL_TOKEN=")][0]


def probe_java(prompt: str, run: int) -> tuple[float, float]:
    """经 Java /conversation/message/stream：建会话 → SSE 流式 → 断言 [DONE]。"""
    h = {"satoken": httpx.post(f"{JAVA}/user/login",
                              json={"username": "admin", "password": admin},
                              timeout=30).json()["data"]}
    conv = httpx.post(f"{JAVA}/conversation", json={"title": f"b2-probe-{run}"},
                      headers=h, timeout=30).json()["data"]["id"]
    t0 = time.perf_counter()
    t_first = None
    done = False
    with httpx.stream("POST", f"{JAVA}/conversation/message/stream",
                      json={"conversationId": conv, "content": prompt, "requestId": f"b2-{run}"},
                      headers=h, timeout=120) as r:
        for line in r.iter_lines():
            if t_first is None and line and '"content"' in line and '""' not in line[:60]:
                t_first = time.perf_counter() - t0
            if line and "[DONE]" in line:
                done = True
                t_total = time.perf_counter() - t0
    total = t_total if done else time.perf_counter() - t0
    httpx.delete(f"{JAVA}/conversation/{conv}", headers=h, timeout=30)
    return (t_first or -1), total


def probe_python(prompt: str, run: int) -> tuple[float, float]:
    """直连 Python /api/chat stream=true（免 Java 转发）。"""
    token_header = {"X-Internal-Token": py_token, "X-Tenant-Id": "1"}
    t0 = time.perf_counter()
    t_first = None
    done = False
    with httpx.stream("POST", f"{PY}/chat",
                      json={"message": prompt, "knowledge_base_id": 101, "stream": True},
                      headers=token_header, timeout=120) as r:
        for line in r.iter_lines():
            if t_first is None and line and '"content"' in line and '""' not in line[:60]:
                t_first = time.perf_counter() - t0
            if line and "[DONE]" in line:
                done = True
                t_total = time.perf_counter() - t0
    total = t_total if done else time.perf_counter() - t0
    return (t_first or -1), total


def main() -> None:
    rounds = 4
    print(f"{'轮':>3} {'链路':>8} {'TTFB':>7} {'总耗时':>8}")
    jf, jt, pf, pt = [], [], [], []
    for i in range(rounds):
        prompt = f"用一句话介绍智能音箱S1的唤醒词（探测轮次{time.time_ns()}）"
        tf, tt = probe_java(f"{prompt}", i)
        print(f"{i:>3} {'Java':>8} {tf*1000:>6.0f}f {tt*1000:>7.0f}f")
        jf.append(tf)
        jt.append(tt)
        tf2, tt2 = probe_python(f"{prompt}", i)
        print(f"{i:>3} {'Python':>8} {tf2*1000:>6.0f}f {tt2*1000:>7.0f}f")
        pf.append(tf2)
        pt.append(tt2)
    print("\n== 分段均值 ==")
    print(f"Java 转发 : TTFB={sum(jf)/rounds*1000:.0f}ms  全流={sum(jt)/rounds*1000:.0f}ms")
    print(f"Python直连: TTFB={sum(pf)/rounds*1000:.0f}ms  全流={sum(pt)/rounds*1000:.0f}ms")
    print(f"Java 转发开销（首包差）: {(sum(jf)-sum(pf))/rounds*1000:.0f}ms")


if __name__ == "__main__":
    main()
