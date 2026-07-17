"""评估中枢数据模型 — 模块边界一律 dataclass，禁止裸 dict。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalSample:
    """一条评估样本（输入侧）。"""

    query_id: str
    query: str
    expected_document_ids: list[str] = field(default_factory=list)
    # 该样本是否要求触发 RAG 检索（行为红线指标的判定依据）
    requires_rag: bool = True
    # 参考答案（有则参与 LLM 正确性评审；无则跳过该指标）
    ground_truth: str | None = None
    # 任意维度标签（intent/difficulty/trap...），用于分切片汇总
    tags: dict[str, str] = field(default_factory=dict)
    # ── 多轮/记忆扩展 ──────────────────────────────────────────────
    # 常规多轮：探测请求附带的对话历史（[{role, content}]）
    history: list[dict[str, str]] = field(default_factory=list)
    # 长期记忆 case：非空时走记忆流程——先以 seed_messages 调
    # /api/internal/memory/consolidate 固化记忆，再以空 history 探测 query
    seed_messages: list[dict[str, str]] = field(default_factory=list)
    # 记忆归属用户（探测请求以此身份触发长期记忆注入）
    user_id: int | None = None
    conversation_id: int | None = None


@dataclass
class EvalRecord:
    """一条已记录的运行结果（record 阶段产物，可反复重放评分）。"""

    query_id: str
    query: str
    answer: str
    ttft_ms: float | None          # 首个内容分块到达时间（流式）
    latency_ms: float                 # 总耗时
    final_status: str                 # completed | error | timeout | cancelled
    requires_rag: bool
    expected_document_ids: list[str] = field(default_factory=list)
    retrieved_document_ids: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    ground_truth: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    recorded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalRecord":
        known = {f for f in cls.__dataclass_fields__}  # noqa: RUF012
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class CaseMetric:
    """单样本的评分明细。"""

    query_id: str
    metrics: dict[str, float] = field(default_factory=dict)
    # LLM 评审不可执行时的原因（如缺参考答案、评审模型异常）
    skip_reason: str | None = None
    flags: list[str] = field(default_factory=list)  # 行为红线命中标记


@dataclass
class MetricResult:
    """评分阶段产物：overall 聚合 + 逐样本明细 + 元信息。"""

    run_file: str
    overall: dict[str, float]
    cases: list[CaseMetric] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_file": self.run_file,
            "overall": self.overall,
            "cases": [
                {"query_id": c.query_id, "metrics": c.metrics,
                 "skip_reason": c.skip_reason, "flags": c.flags}
                for c in self.cases
            ],
            "meta": self.meta,
        }
