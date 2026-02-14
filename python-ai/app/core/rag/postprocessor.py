"""
Postprocessor - 后处理模块
参考 Ragent 项目的 Post Processor 设计

功能:
1. 内容去重 - 相似度去重
2. 分数融合 - 多通道分数归一化
3. 结果排序 - 按相关性排序
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field

from app.utils.config import config


@dataclass
class ProcessedResult:
    """处理后的结果"""
    content: str
    score: float
    document_id: str
    knowledge_base_id: Optional[int] = None
    outline_path: List[str] = field(default_factory=list)
    source: str = "vector"  # 来源: vector/keyword/graph
    metadata: Dict = field(default_factory=dict)


class Postprocessor:
    """后处理器"""

    def __init__(
        self,
        dedup_threshold: float = 0.95,
        min_score: Optional[float] = None,
    ):
        """
        初始化后处理器

        Args:
            dedup_threshold: 去重阈值（相似度高于此值视为重复）
            min_score: 最小证据分数阈值；低于该值的片段不得注入回答上下文
        """
        self.dedup_threshold = dedup_threshold
        self.min_score = (
            config.RAG_MIN_EVIDENCE_SCORE if min_score is None else min_score
        )

    def process(
        self,
        results: List[Dict],
        top_k: int = 5
    ) -> List[ProcessedResult]:
        """
        处理检索结果

        Args:
            results: 原始检索结果
            top_k: 返回数量

        Returns:
            处理后的结果列表
        """
        processed, _ = self.process_with_debug(results, top_k=top_k)
        return processed

    def process_with_debug(
        self,
        results: List[Dict],
        top_k: int = 5,
    ) -> tuple[List[ProcessedResult], List[Dict]]:
        """Process results and retain an auditable decision for every input."""
        processed = [self._to_processed(r) for r in results]
        decisions = [
            {
                "input_rank": rank,
                "chunk_id": result.metadata.get("chunk_id"),
                "document_id": result.document_id,
                "source": result.source,
                "score": round(result.score, 6),
                "evidence_score": round(result.metadata.get("evidence_score", result.score), 6),
                "decision": "pending",
            }
            for rank, result in enumerate(processed, start=1)
        ]

        # 2. 过滤低质量证据。Hybrid RRF score represents rank and is not a
        # confidence score, so use the best original channel score when it is
        # present. This keeps P0's "no sufficient evidence" safety contract
        # intact while allowing rank fusion to decide result order.
        evidence_accepted: List[tuple[ProcessedResult, int]] = []
        for index, result in enumerate(processed):
            if result.metadata.get("evidence_score", result.score) < self.min_score:
                decisions[index]["decision"] = "filtered_low_evidence"
            else:
                evidence_accepted.append((result, index))

        # 3. 去重
        deduplicated: List[tuple[ProcessedResult, int]] = []
        for result, index in evidence_accepted:
            duplicate_of = next((
                existing_index
                for existing, existing_index in deduplicated
                if self._calculate_similarity(result.content, existing.content) >= self.dedup_threshold
            ), None)
            if duplicate_of is not None:
                decisions[index]["decision"] = "filtered_duplicate"
                decisions[index]["duplicate_of_input_rank"] = duplicate_of + 1
            else:
                deduplicated.append((result, index))

        # 4. 排序
        deduplicated.sort(key=lambda item: item[0].score, reverse=True)

        # 5. 截取 top_k
        accepted: List[ProcessedResult] = []
        for rank, (result, index) in enumerate(deduplicated, start=1):
            if rank <= top_k:
                decisions[index]["decision"] = "accepted"
                decisions[index]["final_rank"] = rank
                accepted.append(result)
            else:
                decisions[index]["decision"] = "trimmed_top_k"

        return accepted, decisions

    def _to_processed(self, result: Dict) -> ProcessedResult:
        """将字典转换为 ProcessedResult"""
        return ProcessedResult(
            content=result.get("content", ""),
            score=result.get("score", 0),
            document_id=result.get("document_id", ""),
            knowledge_base_id=result.get("knowledge_base_id"),
            outline_path=result.get("outline_path", []),
            source=result.get("source", "vector"),
            metadata=result.get("metadata", {})
        )

    def _deduplicate(self, results: List[ProcessedResult]) -> List[ProcessedResult]:
        """
        去重：移除内容高度相似的结果
        """
        if not results:
            return []

        unique = [results[0]]

        for result in results[1:]:
            is_duplicate = False
            for existing in unique:
                similarity = self._calculate_similarity(
                    result.content,
                    existing.content
                )
                if similarity >= self.dedup_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(result)

        return unique

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算文本相似度（简单实现）
        实际项目中可以使用更好的算法
        """
        if not text1 or not text2:
            return 0.0

        # 简单的字符重叠率
        set1 = set(text1)
        set2 = set(text2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _sort(self, results: List[ProcessedResult]) -> List[ProcessedResult]:
        """
        排序：按分数降序
        """
        return sorted(results, key=lambda x: x.score, reverse=True)

    def merge_results(
        self,
        vector_results: List[Dict],
        keyword_results: Optional[List[Dict]] = None,
        graph_results: Optional[List[Dict]] = None,
        weights: Optional[Dict[str, float]] = None
    ) -> List[Dict]:
        """
        合并多通道检索结果

        Args:
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果
            graph_results: 图谱检索结果
            weights: 各通道权重

        Returns:
            合并后的结果列表
        """
        if weights is None:
            weights = {
                "vector": 0.6,
                "keyword": 0.3,
                "graph": 0.1
            }

        all_results = []

        # 处理向量结果
        for r in vector_results:
            r["source"] = "vector"
            r["score"] = r.get("score", 0) * weights.get("vector", 0.6)
            all_results.append(r)

        # 处理关键词结果
        if keyword_results:
            for r in keyword_results:
                r["source"] = "keyword"
                r["score"] = r.get("score", 0) * weights.get("keyword", 0.3)
                all_results.append(r)

        # 处理图谱结果
        if graph_results:
            for r in graph_results:
                r["source"] = "graph"
                r["score"] = r.get("score", 0) * weights.get("graph", 0.1)
                all_results.append(r)

        # 按分数排序
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return all_results


# 全局实例
_postprocessor: Optional[Postprocessor] = None


def get_postprocessor() -> Postprocessor:
    """获取全局后处理器"""
    global _postprocessor
    if _postprocessor is None:
        _postprocessor = Postprocessor()
    return _postprocessor
