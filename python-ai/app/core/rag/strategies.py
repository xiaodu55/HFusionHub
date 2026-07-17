"""
Classification Strategies - 分类策略实现

包含多种意图分类策略：
- LLMClassificationStrategy: 基于 LLM 的分类（准确，高成本）
- RuleClassificationStrategy: 基于规则的分类（快速，低成本）
- HybridClassificationStrategy: 混合分类（推荐，平衡准确性和成本）
"""

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod

from ..llm import BaseLLM, ChatMessage, get_llm
from .models import ComplexityLevel, DomainType, IntentResult, IntentType

logger = logging.getLogger(__name__)


class ClassificationStrategy(ABC):
    """
    分类策略抽象基类

    定义意图分类的接口规范
    """

    @abstractmethod
    async def classify(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        **kwargs
    ) -> IntentResult:
        """
        分类查询意图

        Args:
            query: 用户查询
            history: 对话历史 [{"role": "user/assistant", "content": "..."}]

        Returns:
            IntentResult 分类结果
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass

    def _get_processing_strategy(
        self,
        intent: IntentType,
        complexity: ComplexityLevel
    ) -> str:
        """
        根据意图和复杂度确定处理策略

        Args:
            intent: 意图类型
            complexity: 复杂度级别

        Returns:
            处理策略名称
        """
        if intent == IntentType.CHITCHAT:
            return "direct_llm"

        if intent == IntentType.OPERATION:
            return "tool_execution"

        if complexity == ComplexityLevel.SIMPLE:
            return "simple_retrieval"

        if complexity == ComplexityLevel.MEDIUM:
            return "multi_query_retrieval"

        if complexity == ComplexityLevel.COMPLEX:
            return "decompose_and_retrieve"

        return "simple_retrieval"


class LLMClassificationStrategy(ClassificationStrategy):
    """
    基于 LLM 的分类策略

    使用大语言模型进行意图分类，准确但成本较高
    """

    def __init__(self, llm: BaseLLM | None = None):
        """
        初始化 LLM 分类策略

        Args:
            llm: LLM 实例（可选，默认使用全局 LLM）
        """
        self.llm = llm
        self._cache: dict[str, IntentResult] = {}

    def _get_llm(self) -> BaseLLM:
        """获取 LLM 实例"""
        if self.llm is None:
            self.llm = get_llm()
        return self.llm

    async def classify(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        **kwargs
    ) -> IntentResult:
        """使用 LLM 分类"""

        # 检查缓存
        cache_key = self._get_cache_key(query, history)
        if cache_key in self._cache:
            logger.debug(f"Cache hit for query: {query[:30]}...")
            return self._cache[cache_key]

        # 构建提示词
        prompt = self._build_prompt(query, history)

        # 调用 LLM
        llm = self._get_llm()
        response = await llm.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0,  # 确定性输出
            max_tokens=200
        )

        # 解析结果
        result = self._parse_response(response.content)

        # 缓存结果
        self._cache[cache_key] = result

        return result

    def _build_prompt(
        self,
        query: str,
        history: list[dict[str, str]] | None
    ) -> str:
        """构建分类提示词"""
        history_text = ""
        if history:
            history_text = "\n".join([
                f"{msg['role']}: {msg['content']}"
                for msg in history[-3:]  # 最近3条
            ])
            history_text = f"\n对话历史：\n{history_text}\n"

        return f"""分析以下用户查询的意图和复杂度。{history_text}
用户查询：{query}

意图说明：
- factual: 事实型问题（是什么/怎么/如何）
- comparison: 对比型（区别/优缺点/比较）
- summary: 总结型（总结/概括/简述）
- operation: 操作型（创建/删除/修改/执行/保存/写入/把…整理成笔记/保存到知识库等需要执行动作的请求）
- chitchat: 闲聊

请返回 JSON 格式（不要包含其他内容）：
{{
    "intent": "factual|comparison|summary|operation|chitchat",
    "complexity": "simple|medium|complex",
    "domain": "tech|business|general",
    "confidence": 0.0-1.0,
    "entities": ["实体1", "实体2"],
    "reasoning": "判断理由"
}}"""

    def _parse_response(self, response: str) -> IntentResult:
        """解析 LLM 响应"""

        # 提取 JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            logger.warning(f"Failed to extract JSON from LLM response: {response[:100]}")
            return IntentResult(
                intent=IntentType.UNKNOWN,
                complexity=ComplexityLevel.SIMPLE,
                domain=DomainType.GENERAL,
                confidence=0.0,
                reasoning="无法解析 LLM 响应"
            )

        try:
            data = json.loads(json_match.group())

            intent = IntentType(data.get("intent", "unknown"))
            complexity = ComplexityLevel(data.get("complexity", "simple"))

            return IntentResult(
                intent=intent,
                complexity=complexity,
                domain=DomainType(data.get("domain", "general")),
                confidence=float(data.get("confidence", 0.5)),
                entities=data.get("entities", []),
                reasoning=data.get("reasoning", ""),
                processing_strategy=self._get_processing_strategy(intent, complexity)
            )
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return IntentResult(
                intent=IntentType.UNKNOWN,
                complexity=ComplexityLevel.SIMPLE,
                domain=DomainType.GENERAL,
                confidence=0.0,
                reasoning=f"解析错误: {e}"
            )

    def _get_cache_key(
        self,
        query: str,
        history: list[dict[str, str]] | None
    ) -> str:
        """生成缓存键"""
        key_data = {
            "query": query,
            "history": history[-3:] if history else []
        }
        return hashlib.md5(
            json.dumps(key_data, ensure_ascii=False).encode()
        ).hexdigest()

    def get_strategy_name(self) -> str:
        return "llm"


class RuleClassificationStrategy(ClassificationStrategy):
    """
    基于规则的分类策略

    使用关键词匹配进行分类，快速但准确度较低
    """

    def __init__(self):
        """初始化规则分类策略"""

        # 意图关键词映射
        self.intent_keywords: dict[IntentType, list[str]] = {
            IntentType.FACTUAL: [
                "是什么", "什么是", "定义", "含义", "解释", "介绍",
                "怎么", "如何", "怎样"
            ],
            IntentType.COMPARISON: [
                "区别", "不同", "比较", "对比", "哪个好", "差异",
                "优缺点", "优点", "缺点", "好处", "坏处"
            ],
            IntentType.SUMMARY: [
                "总结", "概括", "归纳", "摘要", "简述", "概述"
            ],
            IntentType.OPERATION: [
                "帮我", "创建", "删除", "修改", "执行", "添加",
                "更新", "设置", "配置", "安装", "部署",
                # 写操作（笔记/知识库）—— 触发工具路径（write_note 等）
                "保存", "写入", "记录", "整理成", "保存到", "存为",
                "添加到", "写笔记", "保存为", "写入知识库", "保存笔记"
            ],
            IntentType.CHITCHAT: [
                "你好", "谢谢", "再见", "嗨", "您好", "OK",
                "好的", "明白", "知道了"
            ],
        }

        # 复杂度关键词映射
        self.complexity_keywords: dict[ComplexityLevel, list[str]] = {
            ComplexityLevel.SIMPLE: [],  # 默认
            ComplexityLevel.MEDIUM: [
                "和", "以及", "还有", "同时", "并且", "另外"
            ],
            ComplexityLevel.COMPLEX: [
                "为什么", "分析", "解释原因", "原理", "机制",
                "优缺点", "比较", "对比", "哪个好"
            ],
        }

        # 领域关键词映射
        self.domain_keywords: dict[DomainType, list[str]] = {
            DomainType.TECH: [
                "代码", "编程", "Python", "Java", "API", "数据库",
                "服务器", "部署", "开发", "框架", "库", "函数"
            ],
            DomainType.BUSINESS: [
                "销售", "客户", "订单", "财务", "营销", "市场",
                "报表", "业绩", "KPI", "ROI"
            ],
        }

    async def classify(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        **kwargs
    ) -> IntentResult:
        """使用规则分类"""

        # 识别意图
        intent, intent_confidence = self._classify_intent(query)

        # 识别复杂度
        complexity = self._classify_complexity(query)

        # 识别领域
        domain = self._classify_domain(query)

        # 提取实体（简单实现）
        entities = self._extract_entities(query)

        return IntentResult(
            intent=intent,
            complexity=complexity,
            domain=domain,
            confidence=intent_confidence,
            entities=entities,
            reasoning=f"基于规则匹配: intent={intent.value}, complexity={complexity.value}",
            processing_strategy=self._get_processing_strategy(intent, complexity)
        )

    def _classify_intent(self, query: str) -> tuple[IntentType, float]:
        """识别意图"""
        for intent_type, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    return intent_type, 0.8

        # 默认事实查询
        return IntentType.FACTUAL, 0.5

    def _classify_complexity(self, query: str) -> ComplexityLevel:
        """识别复杂度"""
        complexity_score = 0

        for level, keywords in self.complexity_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    complexity_score += 1

        if complexity_score >= 3:
            return ComplexityLevel.COMPLEX
        elif complexity_score >= 1:
            return ComplexityLevel.MEDIUM

        return ComplexityLevel.SIMPLE

    def _classify_domain(self, query: str) -> DomainType:
        """识别领域"""
        for domain, keywords in self.domain_keywords.items():
            for keyword in keywords:
                if keyword.lower() in query.lower():
                    return domain

        return DomainType.GENERAL

    def _extract_entities(self, query: str) -> list[str]:
        """提取实体（简单实现）"""
        entities = []

        # 提取引号内容
        quoted = re.findall(r'[""「](.*?)[""」]', query)
        entities.extend(quoted)

        # 提取英文单词（可能是专有名词）
        english_words = re.findall(r'[A-Za-z][A-Za-z0-9]+', query)
        entities.extend(english_words[:3])  # 最多3个

        return entities[:5]  # 最多5个

    def get_strategy_name(self) -> str:
        return "rule"


class HybridClassificationStrategy(ClassificationStrategy):
    """
    混合分类策略

    先用规则分类，低置信度时用 LLM 分类
    平衡准确性和成本
    """

    def __init__(self, llm: BaseLLM | None = None):
        """
        初始化混合分类策略

        Args:
            llm: LLM 实例（可选）
        """
        self.rule_strategy = RuleClassificationStrategy()
        self.llm_strategy = LLMClassificationStrategy(llm)
        self.confidence_threshold = 0.7

    async def classify(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        **kwargs
    ) -> IntentResult:
        """混合分类：先规则，低置信度时用 LLM"""

        # 1. 先用规则分类（快速，低成本）
        rule_result = await self.rule_strategy.classify(query, history)

        # 2. 如果置信度高，直接返回
        if rule_result.confidence >= self.confidence_threshold:
            logger.debug(f"Rule classification confidence high: {rule_result.confidence:.2f}")
            return rule_result

        # 3. 否则用 LLM 分类（准确，高成本）
        logger.debug(
            f"Rule classification confidence low ({rule_result.confidence:.2f}), "
            f"falling back to LLM"
        )
        llm_result = await self.llm_strategy.classify(query, history)

        # 4. 返回置信度更高的结果
        if llm_result.confidence > rule_result.confidence:
            return llm_result

        return rule_result

    def get_strategy_name(self) -> str:
        return "hybrid"
