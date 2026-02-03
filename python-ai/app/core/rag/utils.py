"""
RAG 公共工具模块

提供 RAG 模块共用的工具函数和常量定义。

作者：Claude
日期：2026-07-22
"""

import re
from typing import List


# =============================================================================
# 常量定义
# =============================================================================

# 评分常量
ENTITY_MATCH_BASE_SCORE = 0.8
NEIGHBOR_RELATION_SCORE = 0.6
CONFIDENCE_BASE_SCORE = 0.6
CONFIDENCE_MAX_SCORE = 1.0
CONFIDENCE_WEIGHT_FACTOR = 0.3

# 压缩常量
DEFAULT_TARGET_RATIO = 0.5
MIN_SENTENCE_LENGTH = 10
MAX_KEY_PHRASES = 5

# Token 估算常量
CHINESE_CHAR_WEIGHT = 1
ENGLISH_WORD_WEIGHT = 1

# 反思质量阈值
DEFAULT_QUALITY_THRESHOLD = 0.7
DEFAULT_MAX_RETRIES = 2

# 路由常量
DEFAULT_CHANNEL_WEIGHT = 1.0
ADAPTIVE_THRESHOLD = 0.2
WEIGHT_MAX_VALUE = 2.0
WEIGHT_MIN_VALUE = 0.0
TIMEOUT_MIN_VALUE = 0.0

# 图谱常量
RELATION_WEIGHT_MIN = 0.0
RELATION_WEIGHT_MAX = 10.0
MAX_PATH_DEPTH = 5


# =============================================================================
# Token 估算工具函数
# =============================================================================

def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量

    使用简单规则：中文字符数 + 英文单词数

    Args:
        text: 输入文本

    Returns:
        估算的 token 数量

    Examples:
        >>> estimate_tokens("你好世界")
        4
        >>> estimate_tokens("Hello World")
        2
        >>> estimate_tokens("Hello 世界")
        3
    """
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + english_words


# =============================================================================
# 关键短语提取工具函数
# =============================================================================

def extract_key_phrases(text: str, max_phrases: int = MAX_KEY_PHRASES) -> List[str]:
    """
    从文本中提取关键短语

    支持提取：
    - 数字（包括小数）
    - 英文术语（首字母大写）
    - 技术术语（包含常见后缀）

    Args:
        text: 输入文本
        max_phrases: 最大返回短语数量

    Returns:
        关键短语列表

    Examples:
        >>> extract_key_phrases("Python 3.9 版本发布")
        ['3.9', 'Python']
        >>> extract_key_phrases("使用 REST API 调用")
        ['REST', 'API']
    """
    key_phrases = []

    # 提取数字
    numbers = re.findall(r'\d+\.?\d*', text)
    key_phrases.extend(numbers[:3])

    # 提取英文术语（首字母大写的单词）
    english_terms = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
    key_phrases.extend(english_terms[:3])

    # 提取技术术语（包含常见后缀）
    tech_patterns = [
        r'[A-Za-z]+API',
        r'[A-Za-z]+SDK',
        r'[A-Za-z]+SQL',
        r'[A-Za-z]+HTTP',
        r'[A-Za-z]+URL',
        r'[A-Za-z]+JSON',
        r'[A-Za-z]+XML',
        r'[A-Za-z]+REST',
        r'[A-Za-z]+CRUD',
    ]
    for pattern in tech_patterns:
        tech_terms = re.findall(pattern, text)
        key_phrases.extend(tech_terms[:2])

    # 去重并限制数量
    return list(set(key_phrases))[:max_phrases]


# =============================================================================
# 文本处理工具函数
# =============================================================================

def split_sentences(text: str, min_length: int = MIN_SENTENCE_LENGTH) -> List[str]:
    """
    将文本分割为句子

    支持中文和英文标点符号

    Args:
        text: 输入文本
        min_length: 最小句子长度

    Returns:
        句子列表

    Examples:
        >>> split_sentences("你好。世界！")
        ['你好。', '世界！']
        >>> split_sentences("Hello. World!")
        ['Hello.', 'World!']
    """
    # 按句号、问号、感叹号分句
    sentences = re.split(r'[。！？.!?]', text)
    # 过滤空句和过短的句子，并添加标点符号
    return [s.strip() + "。" for s in sentences if len(s.strip()) > min_length]


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    计算两个文本的相似度

    使用简单的关键词重叠率

    Args:
        text1: 文本1
        text2: 文本2

    Returns:
        相似度分数 (0-1)

    Examples:
        >>> calculate_text_similarity("Python 编程", "Python 语言")
        0.5
        >>> calculate_text_similarity("Hello World", "Hello World")
        1.0
    """
    if not text1 or not text2:
        return 0.0

    # 提取关键词
    words1 = set(re.findall(r'[\w一-鿿]+', text1.lower()))
    words2 = set(re.findall(r'[\w一-鿿]+', text2.lower()))

    if not words1 or not words2:
        return 0.0

    # 计算重叠率
    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union) if union else 0.0


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断文本

    Args:
        text: 输入文本
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        截断后的文本

    Examples:
        >>> truncate_text("这是一个很长的文本", 5)
        '这是一个很...'
        >>> truncate_text("短文本", 10)
        '短文本'
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
