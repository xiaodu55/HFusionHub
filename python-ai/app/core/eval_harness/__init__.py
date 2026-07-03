"""eval_harness — HFusionHub 离线评估中枢（record/score 分离架构）。

设计来源：ragenteval 工具包的评估方法论，适配 HFusionHub 契约。

两个阶段：
- **record（runner.py）**：驱动生产链路一次 —— SSE 对话流（回答/TTFT/总延迟）
  + 检索评估端点（召回文档与上下文），逐样本落 `data/eval_harness/runs/*.jsonl`；
- **score（score.py）**：重放已记录的运行做评分（可反复重跑/调整权重而不重打 API），
  聚合检索/行为红线/TTFT/LLM-judge 指标 → MetricResult → markdown 报告与 A/B diff。

数据模型一律 dataclass（禁裸 dict 贯穿模块边界）。
"""

from .schemas import EvalRecord, EvalSample, MetricResult

__all__ = ["EvalSample", "EvalRecord", "MetricResult"]
