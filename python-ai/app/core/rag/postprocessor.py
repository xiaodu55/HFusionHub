"""
Postprocessor - 后处理模块
参考 Ragent 项目的 Post Processor 设计

功能:
1. 内容去重 - 相似度去重
2. 分数融合 - 多通道分数归一化
3. 结果排序 - 按相关性排序
"""

import hashlib
import re
from dataclasses import dataclass, field

from app.utils.config import config

# ---- Output-format constraint patterns ----
# These are instructions about HOW to answer, not WHAT to search for.
# Stripping them from query-term extraction prevents false
# query_mismatch filtering.
_OUTPUT_CONSTRAINT_PATTERNS = [
    # English format directives
    re.compile(p, re.IGNORECASE)
    for p in [
        r'\banswer\s+only\s+(?:the\s+)?(?:number|value|result)s?\b',
        r'\b(?:just|only)\s+(?:give|tell|say|output|return)\b',
        r'\b(?:in\s+)?(?:exact|precise|specific)\s+(?:number|value|answer|result)\b',
        r'\b(?:numeric|numerical)\s+(?:value|answer|result|output)\b',
        r'\bplease\s+(?:just\s+)?(?:answer|respond|reply|output)\b',
        r'\b(?:briefly|concisely|shortly)\s+(?:answer|respond)\b',
        r'\bno\s+explanation\b',
        r'\bdon\'?t\s+explain\b',
    ]
    # Chinese format directives
] + [
    re.compile(p)
    for p in [
        r'(?:请|只需|只要)(?:简要|简单|简短|直接)?(?:回答|输出|返回|给出)',
        r'(?:只|仅|就)(?:输出|返回|给出|要)(?:结果|答案|数字|数值)',
        r'(?:不需要|无需|不要|别)(?:解释|说明|描述|啰嗦)',
        r'(?:准确|精确|确切)(?:的)?(?:数字|数值|答案|结果)',
        r'用(?:数字|数值|英文|中文)(?:回答|输出|返回)',
        r'直接(?:说|告诉|回答)',
    ]
]

# Tokens that signal output-format constraints rather than content intent.
# These are stripped AFTER regex pattern matching above.
_OUTPUT_CONSTRAINT_TOKENS: set[str] = {
    "answer", "exact", "exactly", "precise", "precisely", "specific",
    "specifically", "numeric", "numerical", "brief", "briefly", "concise",
    "concisely", "short", "shortly", "only", "just", "output", "return",
    "explain", "explanation", "describe", "description", "tell", "say",
    "回答", "输出", "返回", "给出", "结果", "答案", "数字", "数值",
    "简要", "简单", "简短", "直接", "准确", "精确", "确切", "解释",
    "说明", "描述", "啰嗦", "只需", "只要", "别", "不要", "不需要",
}


# ---- Near-duplicate detection (MinHash + LSH banding) ---------------------
#
# The dedup step used to compare every pair of accepted results with
# character-set Jaccard — O(n^2) set constructions, and a measure that
# over-estimates CJK overlap because common characters dominate the union.
# Replaced by:
#   1. shingle tokenization (words + CJK character bigrams) — far better
#      discrimination for near-duplicate Chinese chunks;
#   2. a 64-length MinHash signature computed once per result (O(|tokens|));
#   3. LSH banding (8 bands x 8 rows) so Jaccard checks only run against
#      genuine candidates — near-linear for retrieval-sized result lists.
#
# At the default 0.95 dedup threshold the band-collision probability is
# 1 - (1 - 0.95^8)^8 ≈ 0.99985, so missing a true near-duplicate is
# effectively impossible; unrelated chunks (sim < 0.7) rarely collide.
_MINHASH_BANDS = 8
_MINHASH_ROWS = 8
_MINHASH_LENGTH = _MINHASH_BANDS * _MINHASH_ROWS  # 64
_REHASH_PRIME = 2654435761  # Knuth multiplicative hash constant
_HASH_SPACE = 1 << 128


def _tokenize(text: str) -> list[str]:
    """Tokenize into words + CJK 2-shingles (adjacent character bigrams)."""
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9_]+", normalized)
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _token_set(text: str | None) -> frozenset | None:
    if not text:
        return None
    return frozenset(_tokenize(text))


def _minhash_signature(tokens: frozenset) -> list[int]:
    """64-length MinHash signature (one md5 digest per token + linear rehash)."""
    signature = [_HASH_SPACE] * _MINHASH_LENGTH
    for token in tokens:
        digest = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest(), "big")
        for i in range(_MINHASH_LENGTH):
            h = (digest + i * _REHASH_PRIME) % _HASH_SPACE
            if h < signature[i]:
                signature[i] = h
    return signature


def _band_keys(signature: list[int]) -> list[tuple]:
    """Return one candidate-bucket key per LSH band."""
    return [
        tuple(signature[i * _MINHASH_ROWS:(i + 1) * _MINHASH_ROWS])
        for i in range(_MINHASH_BANDS)
    ]


@dataclass
class ProcessedResult:
    """处理后的结果"""
    content: str
    score: float
    document_id: str
    knowledge_base_id: int | None = None
    outline_path: list[str] = field(default_factory=list)
    source: str = "vector"  # 来源: vector/keyword/graph
    metadata: dict = field(default_factory=dict)


class Postprocessor:
    """后处理器"""

    def __init__(
        self,
        dedup_threshold: float = 0.95,
        min_score: float | None = None,
        strong_evidence_score: float | None = None,
    ):
        """
        初始化后处理器

        Args:
            dedup_threshold: 去重阈值（相似度高于此值视为重复）
            min_score: 最小证据分数阈值；低于该值的片段不得注入回答上下文
            strong_evidence_score: 强证据分数阈值；达到此值可绕过查询覆盖率检查
        """
        self.dedup_threshold = dedup_threshold
        self.min_score = (
            config.RAG_MIN_EVIDENCE_SCORE if min_score is None else min_score
        )
        self.strong_evidence_score = strong_evidence_score or 0.85

    def process(
        self,
        results: list[dict],
        top_k: int = 5
    ) -> list[ProcessedResult]:
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

    @staticmethod
    def _evidence_score_of(result: "ProcessedResult") -> float:
        """证据分解析：metadata.evidence_score → 重排前原始通道分 → 当前 score。

        重排器（V58 默认 lexical）会把 ``score`` 覆写为覆盖率主导的排序信号，
        它不是置信度。证据门控应使用原始通道分——优先 metadata.evidence_score
        （混合检索管线注入），其次重排器保留的 pre_rerank_score。
        """
        metadata = result.metadata or {}
        for key in ("evidence_score", "pre_rerank_score"):
            value = metadata.get(key)
            if value is not None:
                return float(value)
        return result.score

    def process_with_debug(
        self,
        results: list[dict],
        top_k: int = 5,
        query: str | None = None,
        allow_scoped_summary: bool = False,
    ) -> tuple[list[ProcessedResult], list[dict]]:
        """Process results and retain an auditable decision for every input.

        A whole-KB summary is different from a fact lookup: generic words
        such as "总结" and "资料" cannot achieve normal lexical coverage,
        even when the selected KB has valid candidate chunks.  When the
        caller has already supplied an explicit KB scope, a bounded fallback
        may keep substantive candidates for that summary only.  It never
        applies to an unscoped chat or a normal factual question.
        """
        processed = [self._to_processed(r) for r in results]
        query_terms = self._query_terms(query)

        # ---- 跨通道互认：向量+关键词同时命中的分块视为强证据 ----
        cross_channel_chunks: set[str] = self._find_cross_channel_hits(processed)

        decisions = [
            {
                "input_rank": rank,
                "chunk_id": result.metadata.get("chunk_id"),
                "document_id": result.document_id,
                "source": result.source,
                "score": round(result.score, 6),
                "evidence_score": round(self._evidence_score_of(result), 6),
                "query_coverage": round(self._query_coverage(query_terms, result.content), 6)
                if query_terms else None,
                "decision": "pending",
            }
            for rank, result in enumerate(processed, start=1)
        ]

        # 2. 过滤低质量证据。Hybrid RRF score represents rank and is not a
        # confidence score, so use the best original channel score when it is
        # present. This keeps P0's "no sufficient evidence" safety contract
        # intact while allowing rank fusion to decide result order.
        evidence_accepted: list[tuple[ProcessedResult, int]] = []
        for index, result in enumerate(processed):
            evidence_score = self._evidence_score_of(result)
            chunk_id = result.metadata.get("chunk_id")

            # ---- 三级证据门控 ----
            # Gate 1: 低证据分 → 直接拒绝
            if evidence_score < self.min_score:
                decisions[index]["decision"] = "filtered_low_evidence"
                continue

            # Gate 2: 查询覆盖率 → 任一强证据条件通过即接受
            if self._passes_query_coverage(query_terms, result.content):
                decisions[index]["decision"] = "query_coverage_pass"
                evidence_accepted.append((result, index))
                continue

            # 强证据绕过条件 A: 原始通道相似度达标
            if evidence_score >= self.strong_evidence_score:
                decisions[index]["decision"] = "accepted_strong_evidence"
                decisions[index]["bypass_reason"] = "strong_channel_score"
                evidence_accepted.append((result, index))
                continue

            # 强证据绕过条件 B: 向量+关键词双通道互认
            if chunk_id and chunk_id in cross_channel_chunks:
                decisions[index]["decision"] = "accepted_cross_channel"
                decisions[index]["bypass_reason"] = "cross_channel_corroboration"
                evidence_accepted.append((result, index))
                continue

            # 强证据绕过条件 C: 短查询降低覆盖率门槛
            if len(query_terms) <= 3 and self._query_coverage(query_terms, result.content) >= 0.25:
                decisions[index]["decision"] = "accepted_short_query"
                decisions[index]["bypass_reason"] = "short_query_lenient_coverage"
                evidence_accepted.append((result, index))
                continue

            decisions[index]["decision"] = "filtered_query_mismatch"

        # A scoped summary is allowed to use the best substantive candidates
        # when normal query matching rejected everything.  This keeps the
        # answer grounded in the selected KB while supporting requests such as
        # "总结当前知识库最重要的内容" when vector search is unavailable.
        if allow_scoped_summary and not evidence_accepted:
            summary_min_score = max(0.1, min(self.min_score, 0.15))
            for index, result in enumerate(processed):
                evidence_score = self._evidence_score_of(result)
                compact_content = re.sub(r"\s+", "", result.content or "")
                if evidence_score < summary_min_score or len(compact_content) < 40:
                    continue
                decisions[index]["decision"] = "accepted_scoped_summary"
                decisions[index]["bypass_reason"] = "explicit_knowledge_base_summary"
                evidence_accepted.append((result, index))

        # 3. 去重 — token Jaccard via MinHash + LSH banding (near-linear).
        # Signatures/token sets are computed once per result; exact duplicates
        # hit the content-fingerprint dict; band buckets restrict Jaccard
        # checks to genuine candidates instead of every accepted result.
        deduplicated: list[tuple[ProcessedResult, int]] = []
        content_fingerprints: dict[str, int] = {}  # md5(content) -> kept position
        band_index: dict[tuple, list[int]] = {}  # band key -> kept positions
        kept: list[tuple] = []  # (result, index, token_set, signature)

        for result, index in evidence_accepted:
            content = result.content or ""
            fingerprint = hashlib.md5(content.encode("utf-8")).hexdigest()
            tokens = _token_set(content)
            signature = _minhash_signature(tokens) if tokens else None
            band_keys = _band_keys(signature) if signature is not None else []

            duplicate_pos = content_fingerprints.get(fingerprint)
            if duplicate_pos is None and signature is not None:
                candidates: set[int] = set()
                for key in band_keys:
                    candidates.update(band_index.get(key, ()))
                for pos in sorted(candidates):
                    if self._jaccard_sets(tokens, kept[pos][2]) >= self.dedup_threshold:
                        duplicate_pos = pos
                        break

            if duplicate_pos is not None:
                existing_index = kept[duplicate_pos][1]
                decisions[index]["decision"] = "filtered_duplicate"
                decisions[index]["duplicate_of_input_rank"] = existing_index + 1
            else:
                pos = len(kept)
                kept.append((result, index, tokens, signature))
                content_fingerprints[fingerprint] = pos
                for key in band_keys:
                    band_index.setdefault(key, []).append(pos)
                deduplicated.append((result, index))

        # 4. 排序
        deduplicated.sort(key=lambda item: item[0].score, reverse=True)

        # 5. 截取 top_k
        accepted: list[ProcessedResult] = []
        for rank, (result, index) in enumerate(deduplicated, start=1):
            if rank <= top_k:
                decisions[index]["decision"] = "accepted"
                decisions[index]["final_rank"] = rank
                accepted.append(result)
            else:
                decisions[index]["decision"] = "trimmed_top_k"

        return accepted, decisions

    def _to_processed(self, result: dict) -> ProcessedResult:
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

    def _deduplicate(self, results: list[ProcessedResult]) -> list[ProcessedResult]:
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
        """Token (word + CJK bigram) Jaccard similarity.

        Character-set Jaccard over-estimates CJK overlap because common
        characters dominate the union; shingles capture local ordering and
        discriminate near-duplicate chunks far better.
        """
        return self._jaccard_sets(_token_set(text1), _token_set(text2))

    @staticmethod
    def _jaccard_sets(set1: frozenset | None, set2: frozenset | None) -> float:
        """Jaccard similarity between two precomputed token sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _strip_output_constraints(query: str) -> str:
        """Remove answer-format directives so they don't pollute relevance scoring.

        "Answer only the number what is the test token" -> "what is the test token"
        """
        stripped = query
        for pattern in _OUTPUT_CONSTRAINT_PATTERNS:
            stripped = pattern.sub(" ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        return stripped or query

    @classmethod
    def _query_terms(cls, query: str | None) -> list[str]:
        if not query:
            return []
        stripped = cls._strip_output_constraints(query)
        stopwords = {
            "什么", "怎么", "如何", "为什么", "是否", "多少", "哪里", "哪个",
            "请", "帮", "我", "一下", "这个", "那个", "文档", "内容", "知识库",
            "是", "的", "了", "吗", "呢", "和", "与", "或", "在", "中", "对", "把", "个",
            "什", "么", "怎", "哪", "为", "一", "下", "这", "那", "文", "档", "内", "容",
            "what", "how", "why", "where", "which", "who", "when", "is", "are", "was", "were",
            "the", "a", "an", "of", "in", "on", "for", "to", "do", "does", "did", "please",
            "tell", "me", "about",
        }
        raw_terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", stripped.lower())
        terms: list[str] = []
        for term in raw_terms:
            if term in stopwords or term in _OUTPUT_CONSTRAINT_TOKENS:
                continue
            if len(term) == 1 and not ("\u4e00" <= term <= "\u9fff"):
                continue
            if term not in terms:
                terms.append(term)
        return terms

    @classmethod
    def _find_cross_channel_hits(cls, processed: list[ProcessedResult]) -> set[str]:
        """Return chunk_ids that appear in BOTH vector and keyword channels."""
        vector_ids: set[str] = set()
        keyword_ids: set[str] = set()
        for result in processed:
            chunk_id = result.metadata.get("chunk_id")
            if not chunk_id:
                continue
            if result.source == "vector":
                vector_ids.add(chunk_id)
            elif result.source == "keyword":
                keyword_ids.add(chunk_id)
        return vector_ids & keyword_ids

    @classmethod
    def _query_coverage(cls, query_terms: list[str], content: str) -> float:
        if not query_terms:
            return 1.0
        content_terms = set(cls._query_terms(content))
        if not content_terms:
            return 0.0
        return len(set(query_terms) & content_terms) / len(query_terms)

    @classmethod
    def _passes_query_coverage(cls, query_terms: list[str], content: str) -> bool:
        if not query_terms:
            return True
        coverage = cls._query_coverage(query_terms, content)
        if len(query_terms) <= 2:
            return coverage >= 0.5
        if len(query_terms) <= 3:
            return coverage >= 0.33
        return coverage >= 0.45

    def _sort(self, results: list[ProcessedResult]) -> list[ProcessedResult]:
        """
        排序：按分数降序
        """
        return sorted(results, key=lambda x: x.score, reverse=True)

    def merge_results(
        self,
        vector_results: list[dict],
        keyword_results: list[dict] | None = None,
        graph_results: list[dict] | None = None,
        weights: dict[str, float] | None = None
    ) -> list[dict]:
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
_postprocessor: Postprocessor | None = None


def get_postprocessor() -> Postprocessor:
    """获取全局后处理器"""
    global _postprocessor
    if _postprocessor is None:
        _postprocessor = Postprocessor()
    return _postprocessor
