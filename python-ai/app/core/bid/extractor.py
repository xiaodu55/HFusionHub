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


# ── P1-1：多文件合并 + 评分表解析 ────────────────────────────────────


def merge_documents(documents: List[Dict[str, str]]) -> str:
    """多文件合并（主招标文件 + 澄清/补遗等），为每份来源加标签。

    合并后的文本供 RAG 检索与规则解析共用，来源标签保留可追溯性。
    入参形如 [{"title": "招标公告", "content": "..."}, ...]。
    """
    parts: List[str] = []
    for doc in documents:
        title = (doc.get("title") or "未命名文件").strip()
        content = (doc.get("content") or "").strip()
        if content:
            parts.append(f"【来源文件：{title}】\n{content}")
    return "\n\n".join(parts)


def extract_scoring_points(text: Optional[str]) -> List[Dict[str, object]]:
    """从评分表格文本中确定性抽取评分点（无 LLM）。

    支持行式表格两种常见写法：
      - "技术方案 40 分" / "技术分（40分）"
      - "价格：30 分"
    返回 [{"name": "...", "max_score": 40, "criteria": "..."}]；排除合计/满分行。
    """
    if not text:
        return []
    points: List[Dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip().rstrip("。；;")
        if not line:
            continue
        m = re.match(
            r"^([一-龥A-Za-z0-9（）()·、\-\s]{2,24}?)\s*[:：]?\s*[（(]?(\d+(?:\.\d+)?)\s*分\s*[)）]?$",
            line,
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not name or name.isdigit():
            continue
        if re.search(r"(总计|合计|满分|总得分|总评|总分|序号)", name):
            continue
        score = float(m.group(2))
        if score <= 0:
            continue
        points.append({"name": name, "max_score": score})
    return points


def parse_scoring_points_xlsx(path: str) -> List[Dict[str, object]]:
    """解析 XLSX 评分表为评分点列表（openpyxl 可用时）。

    兼容常见招标评分表布局：第一列为评分项名称，分值列为含"NN 分"文本或纯数字。
    openpyxl 不可用、路径无效或解析失败时返回空列表（调用方自行降级）。
    """
    try:
        from openpyxl import load_workbook  # 可选依赖，缺失时降级
    except ImportError:
        return []
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return []
    points: List[Dict[str, object]] = []
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                if not row:
                    continue
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if not cells:
                    continue
                name: Optional[str] = None
                score: Optional[float] = None
                for cell in cells:
                    m = re.search(r"(\d+(?:\.\d+)?)\s*分", cell)
                    if m and score is None:
                        score = float(m.group(1))
                        continue
                    if not cell.isdigit() and name is None:
                        name = cell
                if name and score and score > 0 and not re.search(r"(总计|合计|满分|总得分|序号)", name):
                    points.append({"name": name[:80], "max_score": score})
    finally:
        wb.close()
    return points
