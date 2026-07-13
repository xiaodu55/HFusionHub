"""QueryRewriter 查询重写器单元测试。

覆盖:
- 上下文补充（指代词替换）
- 复合问题拆分（问号 / 分隔符）
- 术语扩展
- RewriteResult 字段语义与 get_query_rewriter 单例
"""

import pytest

from app.core.rag.query_rewriter import QueryRewriter, RewriteResult, get_query_rewriter


@pytest.fixture
def rewriter() -> QueryRewriter:
    return QueryRewriter()


class TestRewriteResult:
    """RewriteResult 数据结构。"""

    def test_defaults(self):
        result = RewriteResult(original_query="q", rewritten_queries=["q"])
        assert result.context_added is False
        assert result.split_count == 1


class TestRewriteSplit:
    """多问题拆分。"""

    def test_question_mark_split(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Python是什么?它有什么优势?")
        assert result.rewritten_queries == ["Python是什么?", "它有什么优势?"]
        assert result.split_count == 2

    def test_chinese_question_mark_split(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("什么是RAG？为什么需要它？")
        assert len(result.rewritten_queries) == 2
        assert all(q.endswith("？") for q in result.rewritten_queries)

    def test_separator_split_when_no_question_mark(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("苹果和香蕉哪个好")
        assert result.rewritten_queries == ["苹果", "香蕉哪个好"]
        assert result.split_count == 2

    def test_single_question_unchanged(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("什么是向量数据库？")
        assert result.rewritten_queries == ["什么是向量数据库？"]
        assert result.split_count == 1

    def test_no_question_mark_no_separator(self, rewriter: QueryRewriter):
        """无问号无分隔符的查询：沿用既有行为，补半角问号。"""
        result = rewriter.rewrite("你好呀")
        assert result.rewritten_queries == ["你好呀?"]


class TestRewriteContext:
    """上下文补充（指代替换）。"""

    HISTORY = [
        {"role": "user", "content": "我想了解「iPhone 15」的参数"},
        {"role": "assistant", "content": "iPhone 15 的参数如下……"},
        {"role": "user", "content": "它多少钱？"},
    ]

    def test_pronoun_replaced_with_recent_entity(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("它多少钱？", conversation_history=self.HISTORY)
        assert result.rewritten_queries == ["iPhone 15多少钱？"]
        assert result.context_added is True

    def test_original_query_preserved(self, rewriter: QueryRewriter):
        """original_query 应保留用户原始输入（替换前）。"""
        result = rewriter.rewrite("它多少钱？", conversation_history=self.HISTORY)
        assert result.original_query == "它多少钱？"

    def test_no_pronoun_query_unchanged(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("iPhone 15多少钱？", conversation_history=self.HISTORY)
        assert result.rewritten_queries == ["iPhone 15多少钱？"]
        assert result.context_added is True

    def test_pronoun_without_history_entity_unchanged(self, rewriter: QueryRewriter):
        history = [{"role": "user", "content": "你好"}]
        result = rewriter.rewrite("它多少钱？", conversation_history=history)
        assert result.rewritten_queries == ["它多少钱？"]

    def test_no_history_marks_context_not_added(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("什么是RAG？")
        assert result.context_added is False


class TestExtractRecentEntities:
    """历史实体提取。"""

    def test_only_user_messages_counted(self, rewriter: QueryRewriter):
        history = [
            {"role": "assistant", "content": "推荐「A」和「B」"},
            {"role": "user", "content": "对比「C」"},
        ]
        entities = rewriter._extract_recent_entities(history)
        assert entities == ["C"]

    def test_max_three_entities(self, rewriter: QueryRewriter):
        history = [
            {"role": "user", "content": "看「一」「二」「三」「四」"},
        ]
        entities = rewriter._extract_recent_entities(history)
        assert len(entities) == 3


class TestExpandTerms:
    """术语扩展。"""

    def test_expand_with_mapping(self, rewriter: QueryRewriter):
        result = rewriter.expand_terms("什么是LLM", {"LLM": ["大语言模型"]})
        assert result == ["什么是LLM", "什么是大语言模型"]

    def test_expand_without_mapping(self, rewriter: QueryRewriter):
        assert rewriter.expand_terms("什么是LLM") == ["什么是LLM"]
        assert rewriter.expand_terms("什么是LLM", {}) == ["什么是LLM"]

    def test_expand_term_not_in_query(self, rewriter: QueryRewriter):
        result = rewriter.expand_terms("什么是RAG", {"LLM": ["大语言模型"]})
        assert result == ["什么是RAG"]


class TestSingleton:
    """get_query_rewriter 全局单例。"""

    def test_returns_same_instance(self):
        assert get_query_rewriter() is get_query_rewriter()
