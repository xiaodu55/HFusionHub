"""评估中枢数据模型 — 模块边界一律 dataclass，禁止裸 dict。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalSample:
    """一条评估样本（输入侧）。"""

    query_id: str
    query: str
    expected_document_ids: List[str] = field(default_factory=list)
    # 该样本是否要求触发 RAG 检索（行为红线指标的判定依据）
    requires_rag: bool = True
    # 参考答案（有则参与 LLM 正确性评审；无则跳过该指标）
    ground_truth: Optional[str] = None
    # 任意维度标签（intent/difficulty/trap...），用于分切片汇总
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class EvalRecord:
    """一条已记录的运行结果（record 阶段产物，可反复重放评分）。"""

    query_id: str
    query: str
    answer: str
    ttft_ms: Optional[float]          # 首个内容分块到达时间（流式）
    latency_ms: float                 # 总耗时
    final_status: str                 # completed | error | timeout | cancelled
    requires_rag: bool
    expected_document_ids: List[str] = field(default_factory=list)
    retrieved_document_ids: List[str] = field(default_factory=list)
    contexts: List[str] = field(default_factory=list)
    ground_truth: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    recorded_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalRecord":
        known = {f for f in cls.__dataclass_fields__}  # noqa: RUF012
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class CaseMetric:
    """单样本的评分明细。"""

    query_id: str
    metrics: Dict[str, float] = field(default_factory=dict)
    # LLM 评审不可执行时的原因（如缺参考答案、评审模型异常）
    skip_reason: Optional[str] = None
    flags: List[str] = field(default_factory=list)  # 行为红线命中标记


@dataclass
class MetricResult:
    """评分阶段产物：overall 聚合 + 逐样本明细 + 元信息。"""

    run_file: str
    overall: Dict[str, float]
    cases: List[CaseMetric] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
