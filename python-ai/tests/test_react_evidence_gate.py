"""A4 证据门与 groundedness 守卫单测。

覆盖 react 管线中"答不答"决策的确定性判据：
- ``ReactAgent._below_evidence_gate``：检索最高融合分 vs 路由置信阈值；
- ``ReactAgent._answer_support_score``：答案对上下文的词汇支持度；
- ``ReactAgent._is_groundless_answer``：文案匹配 OR 分数判据（A4 修洞）。
"""

from app.core.agent.react import ReactAgent

_GROUNDED_CONTEXT = (
    "智能音箱 S1 支持两个唤醒词：小帆小帆与云帆云帆。"
    "内置 5W 扬声器，支持 Wi-Fi 6 与蓝牙 5.3 连接。"
)


# ---------------------------------------------------------------------------
# 证据门（routing.confidence_threshold 的消费方）
# ---------------------------------------------------------------------------

def test_below_evidence_gate_false_for_strong_evidence():
    sources = [{"score": 0.92}, {"score": 0.41}]
    assert ReactAgent._below_evidence_gate(sources, threshold=0.7) is False


def test_below_evidence_gate_true_for_weak_evidence():
    sources = [{"score": 0.31}, {"score": 0.28}]
    assert ReactAgent._below_evidence_gate(sources, threshold=0.7) is True


def test_below_evidence_gate_false_for_empty_sources():
    # 空检索结果不归证据门管（由空上下文分支处理）
    assert ReactAgent._below_evidence_gate([], threshold=0.7) is False


def test_below_evidence_gate_treats_missing_score_as_zero():
    sources = [{"score": None}, {"other": 1.0}]
    assert ReactAgent._below_evidence_gate(sources, threshold=0.7) is True


def test_evidence_gate_threshold_defaults_off(monkeypatch):
    """A4 实测校准：融合分阈值默认关闭（0=不拒答），待 runtime 校准后显式开启。"""
    monkeypatch.delenv("RAG_EVIDENCE_GATE_THRESHOLD", raising=False)
    assert ReactAgent._evidence_gate_threshold() == 0.0
    monkeypatch.setenv("RAG_EVIDENCE_GATE_THRESHOLD", "0.7")
    assert ReactAgent._evidence_gate_threshold() == 0.7
    monkeypatch.setenv("RAG_EVIDENCE_GATE_THRESHOLD", "not-a-number")
    assert ReactAgent._evidence_gate_threshold() == 0.0


# ---------------------------------------------------------------------------
# 词汇支持分（ReflectionConfig.confidence_threshold 的消费方判据）
# ---------------------------------------------------------------------------

def test_answer_support_score_high_for_grounded_answer():
    answer = "智能音箱 S1 支持「小帆小帆」与「云帆云帆」两个唤醒词 [1]。"
    score, has_substantial = ReactAgent._answer_support_score(answer, _GROUNDED_CONTEXT)
    assert has_substantial is True
    assert score >= 0.6


def test_answer_support_score_low_for_hallucinated_answer():
    answer = "云帆智能公司的创始人张三于 1999 年创立该公司，总部位于深圳市南山区科技园。"
    score, has_substantial = ReactAgent._answer_support_score(answer, _GROUNDED_CONTEXT)
    assert has_substantial is True
    assert score < 0.3


def test_answer_support_score_skips_short_sentences():
    # 全部为短应答句时无实质句可判，has_substantial=False
    score, has_substantial = ReactAgent._answer_support_score(
        "是的。好的。", _GROUNDED_CONTEXT)
    assert has_substantial is False
    assert score == 0.0


def test_answer_support_score_empty_inputs():
    assert ReactAgent._answer_support_score("", _GROUNDED_CONTEXT) == (0.0, False)
    assert ReactAgent._answer_support_score("一些回答内容。", "") == (0.0, False)


# ---------------------------------------------------------------------------
# groundedness 守卫（A4 修洞：文案匹配 OR 分数判据）
# ---------------------------------------------------------------------------

def test_is_groundless_answer_marker_match_without_context():
    assert ReactAgent._is_groundless_answer("抱歉，未检索到足够依据。") is True


def test_is_groundless_answer_grounded_answer_passes():
    answer = "智能音箱 S1 支持「小帆小帆」与「云帆云帆」两个唤醒词 [1]。"
    assert ReactAgent._is_groundless_answer(
        answer, _GROUNDED_CONTEXT, confidence_threshold=0.6) is False


def test_is_groundless_answer_score_catches_hallucination():
    """A4 修洞②：完全脱离资料的幻觉答案即使不包含固定文案也被判无依据。"""
    answer = "云帆智能公司的创始人张三于 1999 年创立该公司，总部位于深圳市南山区科技园。"
    assert ReactAgent._is_groundless_answer(
        answer, _GROUNDED_CONTEXT, confidence_threshold=0.6) is True


def test_is_groundless_answer_short_answer_not_judged_by_score():
    # 短应答无实质句，分数判据不参与（避免误杀"是的。"这类回答）
    assert ReactAgent._is_groundless_answer(
        "是的。", _GROUNDED_CONTEXT, confidence_threshold=0.6) is False


def test_is_groundless_answer_without_context_keeps_legacy_behavior():
    """context 缺省时仅做文案匹配（旧调用方行为不变）。"""
    assert ReactAgent._is_groundless_answer("正常回答内容，不含固定文案。") is False
