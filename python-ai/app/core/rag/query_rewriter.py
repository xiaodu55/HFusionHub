"""
Query Rewriter - 问题重写模块
参考 Ragent 项目的 Query Rewriter 设计

功能:
1. 上下文补充 - 处理指代问题
2. 多问题拆分 - 复合问题分解
3. 术语映射 - 领域术语扩展
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class RewriteResult:
    """重写结果"""
    original_query: str
    rewritten_queries: List[str]
    context_added: bool = False
    split_count: int = 1


class QueryRewriter:
    """问题重写器"""

    def __init__(self):
        # 指代词列表
        self.pronouns = ["它", "这个", "那个", "这些", "那些", "他", "她", "这里", "那里"]
        # 分隔符模式
        self.split_patterns = [
            r"[;；]",
            r"[,，]",
            r"还有",
            r"另外",
            r"以及",
            r"和",
        ]

    def rewrite(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> RewriteResult:
        """
        重写用户查询

        Args:
            query: 用户原始查询
            conversation_history: 对话历史

        Returns:
            RewriteResult 重写结果
        """
        # 1. 上下文补充（处理指代）
        if conversation_history:
            query = self._add_context(query, conversation_history)

        # 2. 多问题拆分
        queries = self._split_query(query)

        return RewriteResult(
            original_query=query,
            rewritten_queries=queries,
            context_added=bool(conversation_history),
            split_count=len(queries)
        )

    def _add_context(
        self,
        query: str,
        history: List[Dict]
    ) -> str:
        """
        添加上下文（处理指代问题）

        例如: "它多少钱?" -> "iPhone 15 多少钱?"
        """
        # 检查是否包含指代词
        has_pronoun = any(p in query for p in self.pronouns)
        if not has_pronoun:
            return query

        # 从历史中提取最近的实体
        recent_entities = self._extract_recent_entities(history)
        if not recent_entities:
            return query

        # 替换指代词
        context_query = query
        for pronoun in self.pronouns:
            if pronoun in context_query:
                # 用最近的实体替换
                context_query = context_query.replace(pronoun, recent_entities[0], 1)
                break

        return context_query

    def _extract_recent_entities(self, history: List[Dict]) -> List[str]:
        """从对话历史中提取最近的实体"""
        entities = []

        # 遍历历史消息（最近5条）
        for msg in history[-5:]:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                # 简单提取引号内容或大写开头的词
                # 实际项目中可以用 NER 模型
                quoted = re.findall(r'[""「](.*?)[""」]', content)
                entities.extend(quoted)

        return entities[:3]  # 返回最近3个实体

    def _split_query(self, query: str) -> List[str]:
        """
        拆分复合问题

        例如: "Python是什么? 它有什么优势?" -> ["Python是什么?", "它有什么优势?"]
        """
        # 按问号拆分
        parts = re.split(r'[?？]', query)
        queries = []

        for part in parts:
            part = part.strip()
            if part:
                # 如果不是以问号结尾，加上问号
                if not part.endswith('?') and not part.endswith('？'):
                    part += '?'
                queries.append(part)

        # 如果没有问号，检查分隔符
        if len(queries) <= 1:
            for pattern in self.split_patterns:
                if re.search(pattern, query):
                    queries = re.split(pattern, query)
                    queries = [q.strip() for q in queries if q.strip()]
                    break

        return queries if queries else [query]

    def expand_terms(
        self,
        query: str,
        term_mapping: Optional[Dict[str, List[str]]] = None
    ) -> List[str]:
        """
        术语扩展

        Args:
            query: 查询文本
            term_mapping: 术语映射表

        Returns:
            扩展后的查询列表
        """
        if not term_mapping:
            return [query]

        expanded = [query]

        for term, synonyms in term_mapping.items():
            if term in query:
                for synonym in synonyms:
                    expanded.append(query.replace(term, synonym))

        return expanded


# 全局实例
_query_rewriter: Optional[QueryRewriter] = None


def get_query_rewriter() -> QueryRewriter:
    """获取全局问题重写器"""
    global _query_rewriter
    if _query_rewriter is None:
        _query_rewriter = QueryRewriter()
    return _query_rewriter
