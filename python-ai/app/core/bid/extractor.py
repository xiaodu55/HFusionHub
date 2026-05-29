"""招投标规则抽取工具（确定性、无 LLM，便于测试与交叉校验）。

与 LLM 结构化抽取配合：规则结果用于 1) 交叉校验 LLM 输出的评分方式，
2) 在 LLM 不可用时提供基础兜底。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# 评分方式：最低价法 特征（按优先级）
_LOWEST_PRICE_PATTERNS: List[str] = [
    r"经评审的最低投标价(?:法)?",
    r"最低评标价法",
    r"最低投标报价法",
    r"最低报价法",
    r"合理低价(?:法)?",
    r"最低价(?:法)?",
]

# 评分方式：综合评分法 特征
_COMPREHENSIVE_PATTERNS: List[str] = [
    r"综合评分法",
    r"综合评估法",
    r"综合打分(?:法)?",
    r"综合评标",
]

# 废标/否决条款关键词（用于人工确认与风险标注）
DISQUALIFICATION_KEYWORDS: tuple = (
    "废标",
    "否决投标",
    "无效投标",
    "投标无效",
    "取消投标资格",
    "视为废标",
    "不予受理",
    "拒绝投标",
)

# 实质性响应条款关键词
SUBSTANTIVE_RESPONSE_KEYWORDS: tuple = (
    "实质性响应",
    "实质性要求",
    "★",
    "△",
    "必须响应",
    "不得偏离",
)

# 要素键（与 Java 侧 tender_element.element_key 枚举保持一致）
ELEMENT_KEYS: tuple = (
    "tender_number",
    "budget",
    "qualification_requirements",
    "scoring_method",
    "deadline",
    "bid_bond",
    "disqualification_clauses",
    "substantive_response_clauses",
    "bid_currency",
    "contact",
)


def detect_method_type(text: Optional[str]) -> str:
    """从文本中识别评分方式：lowest_price | comprehensive。

    最低价法特征优先匹配（如"经评审的最低投标价法"含"最低价"），
    未命中时默认综合评分法（国内政府采购最常见）。
    """
    if not text:
        return "comprehensive"
    for pattern in _LOWEST_PRICE_PATTERNS:
        if re.search(pattern, text):
            return "lowest_price"
    for pattern in _COMPREHENSIVE_PATTERNS:
        if re.search(pattern, text):
            return "comprehensive"
    return "comprehensive"


def extract_disqualification_clauses(text: Optional[str]) -> List[str]:
    """抽取含废标/否决关键词的条款句子（近似按句切分）。"""
    if not text:
        return []
    sentences = re.split(r"[。；;\n]+", text)
    clauses: List[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if any(kw in s for kw in DISQUALIFICATION_KEYWORDS):
            clauses.append(s)
    return clauses


def parse_scoring_method(text: Optional[str]) -> Dict[str, object]:
    """规则版评分办法解析：返回 {method_type, matches} 供交叉校验。

    LLM 结构化抽取失败时可作为降级依据；score 为命中特征数。
    """
    if not text:
        return {"method_type": "comprehensive", "score": 0, "matched": []}
    method_type = detect_method_type(text)
    matched = []
    patterns = _COMPREHENSIVE_PATTERNS if method_type == "comprehensive" else _LOWEST_PRICE_PATTERNS
    for pattern in patterns:
        if re.search(pattern, text):
            matched.append(pattern)
    return {"method_type": method_type, "score": len(matched), "matched": matched}
