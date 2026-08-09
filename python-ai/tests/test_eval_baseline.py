"""Tests for the Phase-1 evaluation baseline:

- suite build determinism and reference validity
- fixed-format metric aggregation
- baseline diff / regression detection
- hermetic synthetic router determinism
"""

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest
from eval_baseline import (
    CaseOutcome,
    Metrics,
    aggregate_metrics,
    check_gates,
    compression_surviving_chunks,
    compute_citation_faithfulness,
    compute_citation_f1,
    compute_citation_recall,
    diff_against_baseline,
    load_baseline,
    load_cases,
    save_baseline,
    select_cited_chunks,
)

from app.core.rag.synthetic_index import (
    SyntheticIndex,
    SyntheticRouter,
    _extract_sections,
    tokenize,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # python-ai/
SUITE_DIR = PROJECT_ROOT / "evaluation" / "suite"
KB_DIR = PROJECT_ROOT / "evaluation" / "kb"


def _load_module(name: str, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Suite construction
# ---------------------------------------------------------------------------

def test_suite_has_required_size_and_categories():
    suite_manifest = json.loads((SUITE_DIR / "suite_manifest.json").read_text(encoding="utf-8"))
    assert suite_manifest["total_cases"] >= 200
    counts = suite_manifest["category_counts"]
    assert counts["normal"] >= 15
    assert counts["cross_document"] >= 15
    assert counts["refusal"] >= 15
    assert counts["permission"] >= 15
    assert counts["injection"] >= 15
    assert counts["tool"] >= 15
    assert counts["long_document"] >= 15


def test_cases_file_is_pinned_by_suite_manifest():
    suite_manifest = json.loads((SUITE_DIR / "suite_manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((SUITE_DIR / "cases.jsonl").read_bytes()).hexdigest()
    assert digest == suite_manifest["cases_sha256"]


def test_cases_file_is_deterministic_after_rebuild(tmp_path):
    build_suite = _load_module("build_suite", SUITE_DIR / "build_suite.py")
    manifest = json.loads((KB_DIR / "kb_manifest.json").read_text(encoding="utf-8"))
    definitions = _load_module(
        "suite_definitions", SUITE_DIR / "suite_definitions.py"
    )
    cases, _ = build_suite.validate(definitions, manifest)
    assert len(cases) >= 200

    rebuild_path = tmp_path / "rebuild.jsonl"
    build_suite.emit_cases(cases, rebuild_path)
    assert hashlib.sha256(rebuild_path.read_bytes()).hexdigest() == hashlib.sha256(
        (SUITE_DIR / "cases.jsonl").read_bytes()
    ).hexdigest()


def test_all_expected_chunks_exist_in_kb_manifest():
    kb_manifest = json.loads((KB_DIR / "kb_manifest.json").read_text(encoding="utf-8"))
    sections = {
        (doc["doc_id"], section["section_id"])
        for doc in kb_manifest["documents"]
        for section in doc["sections"]
    }
    cases = load_cases(SUITE_DIR / "cases.jsonl")
    for case in cases:
        for chunk in case.expected_chunk_ids:
            doc_id, _, section_id = chunk.partition("#")
            assert (doc_id, section_id) in sections, f"{case.case_id}: {chunk}"


def test_refusal_category_cases_require_refusal_field():
    """类别契约：refusal 类（知识库无答案）必须标 refusal=required，
    否则 runtime 轨 refusal_correctness 永远统计不到它们（A1 修复项）。"""
    cases = load_cases(SUITE_DIR / "cases.jsonl")
    offenders = [c.case_id for c in cases
                 if c.category == "refusal" and c.refusal != "required"]
    assert offenders == []


def test_load_cases_rejects_duplicates(tmp_path):
    path = tmp_path / "cases.jsonl"
    line = json.dumps({
        "id": "x-1", "category": "normal", "query": "q", "kb_id": 101,
        "expected_chunk_ids": ["a#b"], "expected_document_names": ["doc"],
    })
    path.write_text(line + "\n" + line, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate evaluation case id"):
        load_cases(path)


def test_load_cases_rejects_missing_fields(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"id": "x-1", "query": "q"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_cases(path)


# ---------------------------------------------------------------------------
# Synthetic index determinism
# ---------------------------------------------------------------------------

def test_tokenize_is_deterministic():
    text = "智能音箱 S1 支持蓝牙 5.2 与 Wi-Fi 2.4G"
    assert tokenize(text) == tokenize(text)
    assert tokenize(text)
    assert "s1" in tokenize(text)


def test_extract_sections_from_markdown():
    md = "# Doc\n\n## [one] Title A\nbody one\n\n## [two] Title B\nbody two\n"
    sections = _extract_sections(md)
    assert sections == [("one", "Title A\nbody one"), ("two", "Title B\nbody two")]


@pytest.mark.asyncio
async def test_synthetic_router_is_deterministic_and_scoped():
    index = SyntheticIndex()
    router = SyntheticRouter(index=index)
    merged = await router.search("智能音箱 S1 支持哪些唤醒词", index.kb_id, 10)
    first = [(r.metadata["chunk_id"], r.score) for r in merged.results]
    merged_again = await router.search("智能音箱 S1 支持哪些唤醒词", index.kb_id, 10)
    assert first == [(r.metadata["chunk_id"], r.score) for r in merged_again.results]
    assert first[0][0] == "product-catalog#smart-speaker"
    assert all(r.metadata["knowledge_base_id"] == index.kb_id for r in merged.results)


@pytest.mark.asyncio
async def test_synthetic_router_returns_empty_for_foreign_kb():
    router = SyntheticRouter()
    merged = await router.search("任意查询", 999, 5)
    assert merged.results == []


def test_known_queries_retrieve_their_ground_truth():
    index = SyntheticIndex()
    cases = load_cases(SUITE_DIR / "cases.jsonl")
    checked = 0
    for case in cases:
        if not case.expected_chunk_ids or case.category not in ("normal", "long_document"):
            continue
        retrieved = [r.metadata["chunk_id"] for r in index.search_ranked(case.query, 101, 5)]
        assert set(case.expected_chunk_ids) & set(retrieved), case.case_id
        checked += 1
        if checked >= 20:
            break
    assert checked == 20


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------

def _outcome(case_id="c1", category="normal", retrieved=None, expected=None,
             cited=None, faithfulness=None, refusal_expected=False,
             refusal_correct=None, tool=None, tool_success=None,
             latency=None, tokens=None, cost=None, error=None, bid=None):
    return CaseOutcome(
        case_id=case_id,
        category=category,
        retrieved_chunk_ids=retrieved or [],
        expected_chunk_ids=tuple(expected or []),
        expected_document_names=tuple(),
        scope_violations=0,
        citation_faithfulness=faithfulness,
        refusal_expected=refusal_expected,
        refusal_correct=refusal_correct,
        tool=tool,
        cited_chunk_ids=cited or [],
        latency_ms=latency,
        tokens=tokens,
        cost_usd=cost,
        tool_success=tool_success,
        error=error,
        bid=bid,
    )


def test_aggregate_metrics_computes_fixed_format_fields():
    outcomes = [
        _outcome("a", retrieved=["x1", "x2", "x3"], expected=["x1"],
                 cited=["x1", "x2"], faithfulness=1 / 2,
                 latency=100, tokens=500, cost=0.001),
        _outcome("b", retrieved=["y1", "y2", "y3"], expected=["y1", "y2"],
                 cited=["y1"], faithfulness=1.0,
                 latency=300, tokens=700, cost=0.002),
        _outcome("c", retrieved=["z1"], expected=[], cited=[], faithfulness=None,
                 latency=200, tokens=300, cost=0.001),
    ]
    metrics = aggregate_metrics(outcomes, top_k=10)
    # recall@5: (1 + 2) / 3 expected chunks
    assert metrics.recall_at_5 == pytest.approx(1.0)
    # citation accuracy over cases with expected chunks: 2/2
    assert metrics.citation_accuracy == pytest.approx(1.0)
    # mean citation faithfulness over non-null: (0.5 + 1.0)/2
    assert metrics.citation_faithfulness == pytest.approx(0.75)
    # latencies [100, 200, 300]
    assert metrics.p50_latency_ms == pytest.approx(200)
    assert metrics.p95_latency_ms == pytest.approx(300)
    assert metrics.tokens_per_task == pytest.approx(500)
    assert metrics.cost_usd_per_task == pytest.approx((0.001 + 0.002 + 0.001) / 3)
    assert metrics.error_rate == 0.0


def test_aggregate_metrics_reports_citation_recall_and_f1():
    """双报口径：recall 惩罚漏引，F1 为精确率/召回率调和平均。"""
    outcomes = [
        # P=0.5, R=1.0 → F1=2/3
        _outcome("a", retrieved=["x1", "x2"], expected=["x1"],
                 cited=["x1", "x2"], faithfulness=0.5),
        # P=0.5, R=0.5 → F1=0.5
        _outcome("b", retrieved=["y1", "y3"], expected=["y1", "y2"],
                 cited=["y1", "y3"], faithfulness=0.5),
    ]
    metrics = aggregate_metrics(outcomes, top_k=10)
    assert metrics.citation_faithfulness == pytest.approx(0.5)
    assert metrics.citation_recall == pytest.approx(0.75)
    assert metrics.citation_f1 == pytest.approx((2 / 3 + 0.5) / 2)

    # 新指标可设门禁（不低于阈值方向）
    failures = check_gates(metrics, {"citation_recall": 0.9, "citation_f1": 0.9})
    assert any("引用召回率" in f for f in failures)
    assert any("引用 F1" in f for f in failures)
    assert check_gates(metrics, {"citation_recall": 0.5, "citation_f1": 0.5}) == []


def test_aggregate_metrics_bid_domain_fields():
    """招投标领域指标按 case 的 bid 命中率取均值，缺省 case 跳过（B2）。"""
    outcomes = [
        _outcome("a", bid={"qualification_recall": 1.0,
                           "disqualification_clause_recall": 0.5,
                           "scoring_point_accuracy": 1.0}),
        _outcome("b", bid={"qualification_recall": 0.5,
                           "disqualification_clause_recall": 1.0}),
        _outcome("c"),  # 无领域指标
    ]
    metrics = aggregate_metrics(outcomes, top_k=10)

    assert metrics.qualification_recall == pytest.approx(0.75)  # (1.0+0.5)/2
    assert metrics.disqualification_clause_recall == pytest.approx(0.75)  # (0.5+1.0)/2
    assert metrics.scoring_point_accuracy == pytest.approx(1.0)  # 仅 a 有值
    assert metrics.bid_terminology_accuracy is None  # 无该维度


def test_aggregate_metrics_refusal_and_tool():
    outcomes = [
        _outcome("r1", refusal_expected=True, refusal_correct=True),
        _outcome("r2", refusal_expected=True, refusal_correct=False),
        _outcome("t1", tool={"name": "x"}, tool_success=True),
        _outcome("t2", tool={"name": "x"}, tool_success=False),
        _outcome("n1"),
    ]
    metrics = aggregate_metrics(outcomes)
    assert metrics.refusal_correctness == pytest.approx(0.5)
    assert metrics.tool_success_rate == pytest.approx(0.5)


def test_ndcg_math():
    # expected {a, b, c}; retrieved ranks: a@1 (hit), d@2 (miss), c@3 (hit), b@4 (hit)
    outcomes = [
        _outcome("x", retrieved=["a", "d", "c", "b"], expected=["a", "b", "c"]),
    ]
    metrics = aggregate_metrics(outcomes, top_k=10)
    dcg = 1 + 1 / math.log2(4) + 1 / math.log2(5)
    ideal_dcg = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert metrics.ndcg_at_10 == pytest.approx(dcg / ideal_dcg)


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def test_check_gates_respects_direction():
    metrics = Metrics(recall_at_5=0.9, ndcg_at_10=0.7, p95_latency_ms=2500, error_rate=0.01)
    failures = check_gates(metrics, {
        "recall_at_5": 0.95,        # higher is better -> fail
        "ndcg_at_10": 0.60,         # pass
        "p95_latency_ms": 2000,     # lower is better -> fail
        "error_rate": 0.05,         # pass
    })
    assert any("Recall@5" in f for f in failures)
    assert any("P95" in f for f in failures)
    assert len(failures) == 2


def test_check_gates_skips_none_metrics():
    metrics = Metrics(recall_at_5=None, refusal_correctness=None)
    failures = check_gates(metrics, {"recall_at_5": 0.9, "refusal_correctness": 0.9})
    assert failures == []


# ---------------------------------------------------------------------------
# Baseline diff
# ---------------------------------------------------------------------------

def test_diff_against_baseline_detects_quality_regression():
    baseline = {"recall_at_5": 0.95, "ndcg_at_10": 0.90}
    current = Metrics(recall_at_5=0.88, ndcg_at_10=0.90)  # recall dropped 0.07
    deltas, regressions = diff_against_baseline(current, baseline)
    assert deltas["recall_at_5"] == pytest.approx(-0.07)
    assert any("Recall@5" in r for r in regressions)
    assert deltas["ndcg_at_10"] == pytest.approx(0.0)
    assert not any("ndcg_at_10" in r for r in regressions)


def test_diff_against_baseline_allows_small_drop_within_tolerance():
    baseline = {"recall_at_5": 0.95}
    current = Metrics(recall_at_5=0.93)  # drop 0.02 < tolerance 0.03
    _, regressions = diff_against_baseline(current, baseline)
    assert regressions == []


def test_diff_against_baseline_detects_latency_and_cost_increases():
    baseline = {"p95_latency_ms": 1000.0, "tokens_per_task": 500.0}
    current = Metrics(p95_latency_ms=1400.0, tokens_per_task=600.0)
    deltas, regressions = diff_against_baseline(current, baseline)
    # p95 +40% > 20% tolerance
    assert any("P95" in r for r in regressions)
    # tokens +20% > 15% tolerance
    assert any("Token" in r for r in regressions)
    assert deltas["p95_latency_ms"] == pytest.approx(400.0)


def test_baseline_round_trip(tmp_path):
    path = tmp_path / "baseline.json"
    metrics = Metrics(recall_at_5=0.93, p95_latency_ms=1200.0, refusal_correctness=None)
    save_baseline(metrics, path, track="offline", suite_version="1.0.0",
                  kb_version="1.0.0", suite_sha256="sha-abc", generated_at="now")
    loaded = load_baseline(path, required_suite_sha256="sha-abc")
    assert loaded["recall_at_5"] == pytest.approx(0.93)
    assert loaded["p95_latency_ms"] == pytest.approx(1200.0)
    assert loaded["refusal_correctness"] is None


def test_load_baseline_returns_none_when_absent(tmp_path):
    assert load_baseline(tmp_path / "missing.json") is None


def test_load_baseline_rejects_mismatched_suite_sha(tmp_path):
    path = tmp_path / "baseline.json"
    metrics = Metrics(recall_at_5=0.93)
    save_baseline(metrics, path, track="offline", suite_version="1.0.0",
                  kb_version="1.0.0", suite_sha256="sha-old", generated_at="now")
    with pytest.raises(ValueError, match="re-run with --update-baseline"):
        load_baseline(path, required_suite_sha256="sha-new")


def test_load_baseline_rejects_unpinned_baseline(tmp_path):
    # A baseline recorded before the pin existed must not silently compare.
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"metrics": {"recall_at_5": 0.93}}), encoding="utf-8")
    with pytest.raises(ValueError, match="unpinned"):
        load_baseline(path, required_suite_sha256="sha-new")


def test_load_baseline_ignores_sha_when_not_required(tmp_path):
    path = tmp_path / "baseline.json"
    metrics = Metrics(recall_at_5=0.93)
    save_baseline(metrics, path, track="offline", suite_version="1.0.0",
                  kb_version="1.0.0", suite_sha256="sha-old", generated_at="now")
    assert load_baseline(path)["recall_at_5"] == pytest.approx(0.93)


def test_citation_faithfulness_edge_cases():
    assert compute_citation_faithfulness([], ["a#b"]) is None
    assert compute_citation_faithfulness(["a#b", "x#y"], []) is None
    assert compute_citation_faithfulness(["a#b", "x#y"], ["a#b", "c#d"]) == pytest.approx(0.5)


def test_citation_recall_edge_cases():
    # 无期望证据块时无定义；引用空集记 0（什么证据都没覆盖）
    assert compute_citation_recall([], ["a#b"]) == pytest.approx(0.0)
    assert compute_citation_recall(["a#b", "x#y"], []) is None
    assert compute_citation_recall(["a#b", "x#y"], ["a#b", "c#d"]) == pytest.approx(0.5)
    assert compute_citation_recall(["a#b", "c#d"], ["a#b", "c#d"]) == pytest.approx(1.0)


def test_citation_f1_edge_cases():
    assert compute_citation_f1(None, 0.5) is None
    assert compute_citation_f1(0.5, None) is None
    assert compute_citation_f1(0.0, 0.0) == pytest.approx(0.0)
    assert compute_citation_f1(0.5, 1.0) == pytest.approx(2 / 3)


def test_select_cited_chunks_adaptive_window():
    # 检索无命中（首块分数 <= 0）→ 引用空集
    assert select_cited_chunks([], top_k=5, score_ratio=0.5) == []
    assert select_cited_chunks([("a", 0.0), ("b", 0.0)], top_k=5, score_ratio=0.5) == []
    # 首块显著占优 → 窗口收缩到 1 块
    assert select_cited_chunks(
        [("a", 10.0), ("b", 3.0), ("c", 2.0)], top_k=5, score_ratio=0.5
    ) == ["a"]
    # 分数扁平（歧义大）→ 窗口扩张到 top_k 封顶
    assert select_cited_chunks(
        [("a", 10.0), ("b", 9.0), ("c", 8.0), ("d", 1.0)], top_k=3, score_ratio=0.5
    ) == ["a", "b", "c"]
    # 阈值边界：score >= ratio * top1 即引用
    assert select_cited_chunks([("a", 10.0), ("b", 5.0)], top_k=5, score_ratio=0.5) == ["a", "b"]


# 合并后长度超过生产压缩守卫阈值（600 字符）的确定性夹具：
# docA 为数字密集+填充的长段落，docB 与 query 相关但零事实标记、句子短
_COMPRESS_A = (
    "售后政策覆盖全国 128 个城市共 3500 个服务网点，网点数量逐年扩大并延伸到县域市场，具体覆盖范围以官方页面公示为准。"
    "固件自 2024 年起累计更新 26 个版本，每个版本都经过完整的回归测试与灰度发布流程后才会逐步推送。"
    "退换货政策自 2023 年 1 月起执行，签收后 30 天内可无理由退货退款，非质量问题往返运费由客户承担。"
    "整机质保期为 2 年，电池等耗材部件质保 6 个月，人为损坏与进水不在免费保修范围之内。"
    "延保服务可延长至 3 年，价格按整机售价的 8% 计算，购买后 7 天内可无条件全额退订。"
    "以旧换新补贴最高 800 元，需提供旧机购买凭证，补贴以旧机型号与成色评估结果为准。"
    "企业客户批量采购享受 95 折优惠，满 100 台额外赠送 2 年延保与专属客户成功经理服务。"
    "发票自签收日起 15 个工作日内开具，支持增值税专用发票与普通电子发票两种类型。"
    "上门服务覆盖时间为每日 9 点至 18 点，偏远地区上门响应时间可能延长至 5 个工作日。"
    "配件与耗材可以通过官方商城购买，价格以商城实时标价为准，不接受线下渠道议价。"
    "跨境购买与海外保修暂不支持，国行版本与海外版本的服务体系相互独立，请购买前确认清楚。"
    "以上内容为售后条款总则，具体细则以官方公告与合同附件为准，条款如有冲突以最新版本为准。"
    "本段介绍售后政策的适用范围与历史沿革背景说明，帮助用户快速了解服务承诺的整体框架与适用边界。"
)
_COMPRESS_B = "S1 音箱支持自定义唤醒词。唤醒词可以在设置中随时修改。"


@pytest.mark.asyncio
async def test_compression_surviving_chunks_query_signal_flips_survival():
    """A2 核心机制：query 盲区会把相关低事实密度块整块压掉，query 信号救回。"""
    ranked = [("docA#s1", 10.0), ("docB#s1", 8.0)]
    contents = {"docA#s1": _COMPRESS_A, "docB#s1": _COMPRESS_B}
    query = "S1 音箱怎么修改自定义唤醒词"

    # query 盲区（修复前行为）：docB 的句子全部落入选保区之外，chunk 不可见
    assert await compression_surviving_chunks(ranked, contents, "", target_ratio=0.6) \
        == [("docA#s1", 10.0)]
    # 带 query：docB 的句子被 query 重叠信号抬入选保区
    assert await compression_surviving_chunks(ranked, contents, query, target_ratio=0.6) \
        == ranked


@pytest.mark.asyncio
async def test_compression_surviving_chunks_short_context_bypasses_compression():
    """合并文本低于生产短文本保护阈值时不压缩，全部 chunk 可见（与生产一致）。"""
    ranked = [("a#1", 5.0), ("b#1", 4.0)]
    contents = {"a#1": "这是很短的第一段。", "b#1": "这是很短的第二段。"}
    assert await compression_surviving_chunks(ranked, contents, "任意问题",
                                              target_ratio=0.6) == ranked


@pytest.mark.asyncio
async def test_compression_surviving_chunks_ratio_one_disables_simulation():
    """target_ratio=1.0 保留全部句子，等价于关闭压缩模拟。"""
    ranked = [("docA#s1", 10.0), ("docB#s1", 8.0)]
    contents = {"docA#s1": _COMPRESS_A, "docB#s1": _COMPRESS_B}
    assert await compression_surviving_chunks(ranked, contents, "", target_ratio=1.0) \
        == ranked
    assert await compression_surviving_chunks([], contents, "q") == []
