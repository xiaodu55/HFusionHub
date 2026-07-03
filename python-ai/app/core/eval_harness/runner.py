"""record 阶段：驱动生产链路并持久化运行记录。

每条样本产生两次真实调用（与 ragenteval 的 bypass+chat 双调用同构）：
- `POST /api/rag/eval`（生产检索链路 bypass）→ 召回文档 ID 与上下文；
- `POST /api/chat/stream`（SSE 流式对话）→ 回答全文 + TTFT（首个内容分块）+ 总延迟。

结果逐条追加到 `data/eval_harness/runs/<label>_<ts>.jsonl`，供 score 阶段重放评分。
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

import httpx

from .schemas import EvalRecord, EvalSample

_RUNS_DIR = Path("data/eval_harness/runs")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_runs_dir() -> Path:
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return _RUNS_DIR


def new_run_file(label: str, runs_dir: Optional[Path] = None) -> Path:
    """创建本次运行的 JSONL 文件（时间戳命名），返回路径。"""
    directory = runs_dir or default_runs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(ch for ch in label if ch.isalnum() or ch in "-_") or "run"
    return directory / f"{safe_label}_{stamp}.jsonl"


def append_record(run_file: Path, record: EvalRecord) -> None:
    with open(run_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def list_run_files(runs_dir: Optional[Path] = None) -> List[dict]:
    directory = runs_dir or default_runs_dir()
    if not directory.exists():
        return []
    out = []
    for f in sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"file": f.name, "size_bytes": f.stat().st_size,
                    "modified_at": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()})
    return out


def load_run_file(name: str, runs_dir: Optional[Path] = None) -> List[EvalRecord]:
    """按文件名重放运行记录（名称不允许含路径分隔符，防目录穿越）。"""
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("invalid run file name")
    directory = runs_dir or default_runs_dir()
    path = directory / name
    if not path.exists():
        raise FileNotFoundError(f"run file not found: {name}")
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(EvalRecord.from_dict(json.loads(line)))
    return records


def _fetch_retrieval(base_url: str, headers: dict, sample: EvalSample,
                     kb_id: int, top_k: int, timeout: float) -> tuple[List[str], List[str]]:
    """生产检索链路 bypass：返回 (retrieved_document_ids, contexts)。"""
    body = {"query": sample.query, "knowledge_base_id": kb_id, "top_k": top_k, "enable_rewrite": False}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{base_url}/api/rag/eval", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    retrieval = (data.get("retrieval") or {})
    results = retrieval.get("results") or []
    doc_ids = [str(r.get("document_id")) for r in results if r.get("document_id") is not None]
    contexts = [r.get("content") or "" for r in results]
    return doc_ids, contexts


def _run_chat_stream(base_url: str, headers: dict, sample: EvalSample,
                     kb_id: Optional[int], timeout: float) -> tuple[str, Optional[float], float, str]:
    """流式对话：返回 (answer, ttft_ms, latency_ms, final_status)。"""
    body = {"message": sample.query, "stream": True, "request_id": f"eval-{sample.query_id}"}
    if kb_id:
        body["knowledge_base_id"] = kb_id
    answer_parts: List[str] = []
    ttft_ms: Optional[float] = None
    start = time.perf_counter()
    status = "completed"
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        with client.stream("POST", f"{base_url}/api/chat/stream", json=body, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                content = event.get("content") or ""
                if content and not event.get("error"):
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - start) * 1000.0
                    answer_parts.append(content)
                if event.get("error"):
                    status = "error"
    latency_ms = (time.perf_counter() - start) * 1000.0
    return "".join(answer_parts), ttft_ms, latency_ms, status


def run_sample(sample: EvalSample, base_url: str, headers: dict,
               kb_id: int, top_k: int, timeout: float) -> EvalRecord:
    """对单条样本执行记录（检索 bypass + 流式对话）。"""
    retrieved: List[str] = []
    contexts: List[str] = []
    error: Optional[str] = None
    try:
        retrieved, contexts = _fetch_retrieval(base_url, headers, sample, kb_id, top_k, timeout)
    except Exception as exc:  # 检索失败不阻断对话记录，但记入错误
        error = f"retrieval: {type(exc).__name__}: {exc}"[:300]

    try:
        answer, ttft_ms, latency_ms, status = _run_chat_stream(base_url, headers, sample, kb_id, timeout)
    except Exception as exc:
        answer, ttft_ms, latency_ms, status = "", None, 0.0, "error"
        msg = f"chat: {type(exc).__name__}: {exc}"[:300]
        error = f"{error}; {msg}" if error else msg

    return EvalRecord(
        query_id=sample.query_id,
        query=sample.query,
        answer=answer,
        ttft_ms=ttft_ms,
        latency_ms=latency_ms,
        final_status=status,
        requires_rag=sample.requires_rag,
        expected_document_ids=list(sample.expected_document_ids),
        retrieved_document_ids=retrieved,
        contexts=contexts,
        ground_truth=sample.ground_truth,
        tags=sample.tags,
        error=error,
        recorded_at=_now_iso(),
    )


def run_dataset(samples: List[EvalSample], base_url: str, headers: dict,
                kb_id: int, top_k: int = 5, concurrency: int = 4, timeout: float = 180.0,
                runs_dir: Optional[Path] = None, label: str = "run",
                progress: Optional[Callable[[int, int], None]] = None) -> Path:
    """并发执行数据集并逐条持久化（线程安全：主线程统一写文件）。"""
    run_file = new_run_file(label, runs_dir)
    lock = threading.Lock()
    done = 0

    def _work(sample: EvalSample) -> EvalRecord:
        return run_sample(sample, base_url, headers, kb_id, top_k, timeout)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(_work, s): s for s in samples}
        for future in as_completed(futures):
            record = future.result()
            with lock:
                append_record(run_file, record)
                done += 1
                if progress:
                    progress(done, len(samples))
    return run_file
