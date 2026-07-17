"""eval_harness 内核单测：指标纯函数 + runner 持久化 + 评分重放 + A/B 门禁。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.eval_harness import diff as diff_mod
from app.core.eval_harness import runner as runner_mod
from app.core.eval_harness import score as score_mod
from app.core.eval_harness.metrics import behavior, retrieval, ttft
from app.core.eval_harness.schemas import EvalRecord, EvalSample


def _record(qid: str, *, requires_rag=True, retrieved=None, expected=None,
            answer="基于资料的正确回答", ttft=100.0, latency=500.0) -> EvalRecord:
    return EvalRecord(
        query_id=qid, query=f"问题 {qid}", answer=answer,
        ttft_ms=ttft, latency_ms=latency, final_status="completed",
        requires_rag=requires_rag,
        expected_document_ids=list(expected or []),
        retrieved_document_ids=list(retrieved or []),
        ground_truth="参考答案",
    )


# ── 检索指标 ──────────────────────────────────────────────

def test_retrieval_hit_recall_mrr():
    record = _record("q1", retrieved=["7", "8", "9"], expected=["9", "5"])
    case = retrieval.evaluate_case(record, k=5)
    # 第一个期望文档 9 排在检索第 3 位 → MRR=1/3；hit@5=True；recall@5=1/2
    assert case.metrics["hit@5"] == 1.0
    assert case.metrics["recall@5"] == 0.5
    assert case.metrics["mrr@5"] == pytest.approx(1 / 3)


def test_retrieval_miss():
    case = retrieval.evaluate_case(_record("q1", retrieved=["1", "2"], expected=["9"]), k=5)
    assert case.metrics["hit@5"] == 0.0
    assert case.metrics["recall@5"] == 0.0
    assert case.metrics["mrr@5"] == 0.0


def test_retrieval_aggregate_only_requires_rag():
    records = [
        _record("q1", retrieved=["1"], expected=["1"]),
        _record("q2", retrieved=["2"], expected=["1"]),
        # requires_rag=false 的样本不参与检索指标聚合
        _record("q3", requires_rag=False, retrieved=[], expected=["1"]),
    ]
    agg = retrieval.aggregate(records, k=5)
    assert agg["hit@5"] == pytest.approx(0.5)
    assert agg["mrr@5"] == pytest.approx(0.5)


# ── 行为红线 ──────────────────────────────────────────────

def test_behavior_refusal_when_required():
    record = _record("q1", requires_rag=True, retrieved=[], answer="我在当前知识库中未检索到足够依据，无法基于资料回答。")
    flags = behavior.evaluate_case(record).flags
    assert "refusal_when_required" in flags
    assert "fallback_when_required" in flags


def test_behavior_over_retrieval():
    record = _record("q1", requires_rag=False, retrieved=["5"], answer="随便聊聊")
    assert "over_retrieval" in behavior.evaluate_case(record).flags


def test_behavior_aggregate_rates():
    records = [
        _record("q1", requires_rag=True, retrieved=["1"], answer="正常回答"),
        _record("q2", requires_rag=True, retrieved=[], answer="未检索到足够依据"),
        _record("q3", requires_rag=False, retrieved=["9"], answer="过度检索"),
    ]
    agg = behavior.aggregate(records)
    assert agg["fallback_when_required_rate"] == pytest.approx(1 / 3)
    assert agg["over_retrieval_rate"] == pytest.approx(1 / 3)


# ── TTFT ──────────────────────────────────────────────────

def test_ttft_percentile_and_mean():
    records = [
        _record("q1", ttft=100.0, latency=900.0),
        _record("q2", ttft=300.0, latency=1100.0),
        _record("q3", ttft=200.0, latency=1000.0),
    ]
    agg = ttft.aggregate(records)
    assert agg["ttft_p50_ms"] == 200.0
    assert agg["ttft_mean_ms"] == 200.0
    assert agg["latency_mean_ms"] == 1000.0


# ── runner：持久化与重放 ──────────────────────────────────

def test_run_dataset_writes_jsonl_and_replays(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_fetch_retrieval",
                        lambda *a, **k: (["115"], ["上下文片段"]))
    monkeypatch.setattr(runner_mod, "_run_chat_stream",
                        lambda *a, **k: ("模拟回答", 120.0, 800.0, "completed"))

    samples = [
        EvalSample(query_id="q1", query="问题一", expected_document_ids=["115"], requires_rag=True),
        EvalSample(query_id="q2", query="问题二", requires_rag=False),
    ]
    runs_dir = tmp_path / "runs"
    run_file = runner_mod.run_dataset(
        samples, base_url="http://test", headers={"X-Internal-Token": "t"},
        kb_id=132, concurrency=2, runs_dir=runs_dir, label="unit",
    )
    assert run_file.exists()
    records = runner_mod.load_run_file(run_file.name, runs_dir)
    assert len(records) == 2
    by_id = {r.query_id: r for r in records}
    assert by_id["q1"].retrieved_document_ids == ["115"]
    assert by_id["q1"].answer == "模拟回答"
    assert by_id["q1"].ttft_ms == 120.0
    assert by_id["q2"].requires_rag is False

    # 目录穿越防护
    with pytest.raises(ValueError):
        runner_mod.load_run_file("../escape", runs_dir)


# ── score 重放 + diff 门禁 ────────────────────────────────

def test_score_replay_and_diff(tmp_path: Path):
    records = [
        _record("q1", retrieved=["1"], expected=["1"], ttft=500.0, latency=2000.0),
        _record("q2", requires_rag=False, retrieved=["9"], answer="闲聊"),
    ]
    runs_dir = tmp_path / "runs"
    run_file = runner_mod.new_run_file("ab", runs_dir)
    for r in records:
        runner_mod.append_record(run_file, r)

    import asyncio
    result = asyncio.run(score_mod.score_run(run_file.name, runs_dir=runs_dir, enable_judge=False))
    # 检索指标（q1）
    assert result.overall["retrieval_hit@5"] == 1.0
    # 行为指标
    assert result.overall["over_retrieval_rate"] == pytest.approx(1 / 2)
    # TTFT
    assert result.overall["ttft_p50_ms"] == 300.0  # 线性插值中位

    scores_dir = tmp_path / "reports"
    score_mod.save_scores(result, scores_dir)
    loaded = score_mod.load_scores(scores_dir, run_file.name)
    assert loaded["overall"]["retrieval_hit@5"] == 1.0

    # A/B：候选消除过度检索（over_retrieval 0.5 → 0.0，远超 0.02 阈值 → improved）
    candidate = dict(result.overall, over_retrieval_rate=0.0)
    rows = diff_mod.diff_metrics(result.overall, candidate)
    by_metric = {r["metric"]: r for r in rows}
    assert by_metric["over_retrieval_rate"]["verdict"] == diff_mod.IMPROVED
    assert not diff_mod.has_regression(rows)

    # 回归：检索命中率下降超过阈值
    worse = dict(result.overall)
    worse["retrieval_hit@5"] = 0.0
    rows = diff_mod.diff_metrics(result.overall, worse)
    assert diff_mod.has_regression(rows)
    assert {r["verdict"] for r in rows} & {diff_mod.REGRESSED}


# ── API 端到端（TestClient + monkeypatch runner）─────────────────────────

def test_api_runs_and_score_flow(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.eval_harness import runner as runner_mod
    from app.main import app

    client = TestClient(app)
    headers = {"X-Internal-Token": "test-token", "X-Tenant-Id": "1"}

    # 依赖守卫需要 token 一致 —— 直接 monkeypatch 校验函数最省事
    from app.api.deps import require_tenant
    from app.api.internal_auth import require_internal_token
    app.dependency_overrides[require_internal_token] = lambda: None
    app.dependency_overrides[require_tenant] = lambda: 1

    monkeypatch.setattr(runner_mod, "_fetch_retrieval", lambda *a, **k: (["1"], ["ctx"]))
    monkeypatch.setattr(runner_mod, "_run_chat_stream", lambda *a, **k: ("回答", 100.0, 700.0, "completed"))
    monkeypatch.setattr(runner_mod, "default_runs_dir", lambda: tmp_path / "runs")

    # 无样本 → 422
    resp = client.post("/api/eval-harness/run", json={"knowledge_base_id": 132}, headers=headers)
    assert resp.status_code == 422

    # 正常运行（无 judge）
    resp = client.post("/api/eval-harness/run", headers=headers, json={
        "label": "api-test", "knowledge_base_id": 132,
        "samples": [{"query_id": "q1", "query": "问题", "expected_document_ids": ["1"], "requires_rag": True}],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["retrieval_hit@5"] == 1.0

    run_file = body["run_file"]

    # runs 列表
    resp = client.get("/api/eval-harness/runs", headers=headers)
    assert resp.status_code == 200
    assert any(r["file"] == run_file for r in resp.json()["runs"])

    # 报告
    resp = client.get("/api/eval-harness/report", headers=headers, params={"run_file": run_file})
    assert resp.status_code == 200
    assert "评估报告" in resp.json()["report"]

    app.dependency_overrides.clear()


def test_score_by_tag_slicing(tmp_path: Path):
    """切片汇总：带标签样本按维度拆检索指标（intent/difficulty）。"""
    records = [
        _record("q1", retrieved=["1"], expected=["1"]),
        _record("q2", retrieved=["2"], expected=["1"]),
        _record("q3", retrieved=["3"], expected=["1"]),
    ]
    records[0].tags = {"difficulty": "easy"}
    records[1].tags = {"difficulty": "hard"}
    records[2].tags = {"difficulty": "hard"}

    runs_dir = tmp_path / "runs"
    run_file = runner_mod.new_run_file("slice", runs_dir)
    for r in records:
        runner_mod.append_record(run_file, r)

    import asyncio
    result = asyncio.run(score_mod.score_run(run_file.name, runs_dir=runs_dir, enable_judge=False))
    by_diff = result.meta.get("by_tag", {}).get("difficulty", {})
    assert by_diff["easy"]["hit@5"] == 1.0
    assert by_diff["hard"]["hit@5"] == 0.0


# ── runner：长期记忆 case（Batch 1）────────────────────────

class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)


class _FakeStreamContext:
    def __init__(self, lines, sink):
        self._lines = lines
        self._sink = sink

    def __enter__(self):
        return _FakeStreamResponse(self._lines)

    def __exit__(self, *args):
        return False


class _FakeHttpClient:
    """记录请求体的 httpx.Client 替身（支持 stream 上下文与普通 post）。"""

    posts = []
    stream_bodies = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, headers=None, **kwargs):
        _FakeHttpClient.posts.append({"url": url, "json": json, "headers": headers})
        return _FakePostResponse()

    def stream(self, method, url, json=None, headers=None, **kwargs):
        _FakeHttpClient.stream_bodies.append({"url": url, "json": json})
        return _FakeStreamContext(
            ['data: {"content": "记忆回答"}', "data: [DONE]"], _FakeHttpClient.stream_bodies)


class _FakePostResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": {"saved": 1}}


def test_memory_sample_flow_consolidates_then_probes(monkeypatch):
    """seed_messages 非空 → 先同步固化再空 history 探测，产出 requires_rag=False 记录。"""
    consolidate_calls = []
    monkeypatch.setattr(runner_mod, "_consolidate_memory",
                        lambda *a, **k: consolidate_calls.append(a))
    chat_samples = []
    monkeypatch.setattr(runner_mod, "_run_chat_stream",
                        lambda base_url, headers, sample, kb_id, timeout: (
                            chat_samples.append(sample), ("记忆回答", 90.0, 600.0, "completed"))[1])

    sample = EvalSample(
        query_id="mem-001", query="我说过我喜欢什么风格？", requires_rag=False,
        ground_truth="用户偏好简洁风格。",
        tags={"memory_type": "preference"},
        seed_messages=[{"role": "user", "content": "我更喜欢简洁风格。"}],
        user_id=7, conversation_id=990001,
    )
    record = runner_mod.run_sample(sample, "http://test", {"X-Internal-Token": "t"},
                                   kb_id=132, top_k=5, timeout=30)

    assert len(consolidate_calls) == 1
    assert record.requires_rag is False
    assert record.answer == "记忆回答"
    assert record.error is None
    # 探测请求不携带 seed 历史（注入必须来自长期记忆链路）
    assert chat_samples[-1].history == []


def test_consolidate_memory_posts_seed_payload(monkeypatch):
    _FakeHttpClient.posts = []
    _FakeHttpClient.stream_bodies = []
    monkeypatch.setattr(runner_mod.httpx, "Client", _FakeHttpClient)

    sample = EvalSample(
        query_id="mem-042", query="探测", requires_rag=False,
        seed_messages=[{"role": "user", "content": "事实 A"}, {"role": "assistant", "content": "好的"}],
        user_id=3, conversation_id=990042,
    )
    runner_mod._consolidate_memory("http://test", {"X-Internal-Token": "t"},
                                   sample, kb_id=None, timeout=5.0)

    assert len(_FakeHttpClient.posts) == 1
    body = _FakeHttpClient.posts[0]["json"]
    assert _FakeHttpClient.posts[0]["url"].endswith("/api/internal/memory/consolidate")
    assert body["conversation_id"] == 990042
    assert body["user_id"] == 3
    assert body["messages"] == sample.seed_messages


def test_memory_sample_without_conversation_id_gets_stable_fallback(monkeypatch):
    _FakeHttpClient.posts = []
    _FakeHttpClient.stream_bodies = []
    monkeypatch.setattr(runner_mod.httpx, "Client", _FakeHttpClient)

    sample = EvalSample(
        query_id="mem-stable", query="探测", requires_rag=False,
        seed_messages=[{"role": "user", "content": "事实"}],
    )
    runner_mod._consolidate_memory("http://test", {}, sample, kb_id=None, timeout=5.0)
    first = _FakeHttpClient.posts[0]["json"]["conversation_id"]

    runner_mod._consolidate_memory("http://test", {}, sample, kb_id=None, timeout=5.0)
    second = _FakeHttpClient.posts[-1]["json"]["conversation_id"]

    assert first == second and first >= 1  # 同一 query_id 两次调用 conversation_id 稳定


def test_chat_stream_carries_history_and_user_context(monkeypatch):
    _FakeHttpClient.posts = []
    _FakeHttpClient.stream_bodies = []
    monkeypatch.setattr(runner_mod.httpx, "Client", _FakeHttpClient)

    sample = EvalSample(
        query_id="mt-1", query="接着说", requires_rag=False,
        history=[{"role": "user", "content": "我喜欢蓝色"}],
        user_id=5, conversation_id=77,
    )
    answer, ttft, latency, status = runner_mod._run_chat_stream(
        "http://test", {}, sample, kb_id=None, timeout=5.0)

    body = _FakeHttpClient.stream_bodies[0]["json"]
    assert body["history"] == [{"role": "user", "content": "我喜欢蓝色"}]
    assert body["user_id"] == 5
    assert body["conversation_id"] == 77
    assert answer == "记忆回答" and status == "completed"
