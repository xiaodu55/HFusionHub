#!/usr/bin/env python
"""Ground-truth definitions for IT 集成 (it) 行业方案包评测套件 (P2-4).

对应合成知识库 ``evaluation/kb_bid_it``（云谷智慧园区数据中心建设项目，虚构
脱敏）。用例覆盖四类领域指标（经 ``bid_facts`` 透传，评测时在检索命中内容
中做确定性子串匹配，无需 LLM），作为「IT 集成行业方案包」售卖的离线质量凭证。

``build_suite.py`` 校验每个引用对应 kb_manifest 中真实章节，并冻结
``cases.jsonl`` + ``suite_manifest.json``。
"""

from __future__ import annotations

KB_ID = 203

DOC_TITLES = {
    "tender-notice": "云谷智慧园区数据中心建设项目招标公告",
    "bidder-instructions": "投标人须知",
    "evaluation-method": "评标办法",
    "contract-terms": "合同主要条款",
}

# 领域指标维度的期望事实（子串须与语料原文一致，评测时做包含匹配）
QUALIFICATION_FACTS = [
    "电子与智能化工程专业承包一级资质",
    "ITSS 信息技术服务运行维护标准认证",
    "ISO/IEC 27001 信息安全管理体系认证",
    "信息系统项目管理师",
    "资产负债率不得高于 75%",
    "单项合同金额不低于 2000 万元",
]
DISQUALIFICATION_FACTS = [
    "投标报价超过招标预算上限 5800 万元",
    "未按要求提供投标保证金",
    "未提供完整实施方案",
    "串通投标",
    "不具备招标文件要求的资质条件",
]
SCORING_POINT_FACTS = [
    "技术方案 40 分",
    "投标报价 30 分",
    "实施与运维能力 20 分",
    "综合评分法满分 100 分",
    "评标基准价",
]
TERMINOLOGY_FACTS = [
    "投标保证金",
    "实质性响应",
    "系统集成",
    "等级保护三级",
    "服务等级",
    "质量保证金",
    "预付款",
]


def _chunk_ids(*chunks: str) -> list[str]:
    return list(chunks)


def _doc_names(*chunks: str) -> list[str]:
    names: list[str] = []
    for chunk in chunks:
        doc_id = chunk.split("#", 1)[0]
        if doc_id not in DOC_TITLES:
            raise ValueError(f"unknown doc in chunk reference {chunk!r}")
        name = DOC_TITLES[doc_id]
        if name not in names:
            names.append(name)
    return names


def _case(case_id, query, expected, facts, bid_facts=None) -> dict:
    """普通问答类用例；bid_facts 为可选领域指标期望事实。"""
    return {
        "id": case_id,
        "category": "normal",
        "query": query,
        "kb_id": KB_ID,
        "expected_chunk_ids": _chunk_ids(*expected),
        "expected_document_names": _doc_names(*expected),
        "key_facts": list(facts),
        "refusal": "none",
        "risk_labels": [],
        "tool": None,
        "bid_facts": bid_facts,
    }


# ── 资质 / 业绩 / 财务 ───────────────────────────────────────────────

QUALIFICATION_CASES = [
    _case("bidi-q-001", "投标人需要具备什么资质才能参加本项目投标？",
          ("bidder-instructions#qualifications",),
          ("投标人须具备电子与智能化工程专业承包一级资质。",),
          {"qualification_recall": QUALIFICATION_FACTS[:2]}),
    _case("bidi-q-002", "投标人还需要通过哪些体系认证？",
          ("bidder-instructions#qualifications",),
          ("并持有 ITSS 信息技术服务运行维护标准认证与 ISO/IEC 27001 信息安全管理体系认证证书。",),
          {"qualification_recall": [QUALIFICATION_FACTS[1], QUALIFICATION_FACTS[2]]}),
    _case("bidi-q-003", "项目负责人有什么证书要求？",
          ("bidder-instructions#qualifications",),
          ("项目负责人须具备信息系统项目管理师（高级）证书。",),
          {"qualification_recall": [QUALIFICATION_FACTS[3]]}),
    _case("bidi-q-004", "投标人的财务要求是什么，资产负债率有什么限制？",
          ("bidder-instructions#financial",),
          ("投标人近三年财务状况良好，资产负债率不得高于 75%。",),
          {"qualification_recall": [QUALIFICATION_FACTS[4]]}),
    _case("bidi-q-005", "近三年业绩要求是什么？",
          ("bidder-instructions#performance",),
          ("至少完成两项单项合同金额不低于 2000 万元的数据中心或信息系统集成类项目业绩。",),
          {"qualification_recall": [QUALIFICATION_FACTS[5]]}),
]

# ── 废标条款 ─────────────────────────────────────────────────────────

DISQUALIFICATION_CASES = [
    _case("bidi-d-001", "哪些情况会导致废标？",
          ("evaluation-method#disqualification",),
          ("投标报价超过招标预算上限的应当否决其投标。",),
          {"disqualification_clause_recall": DISQUALIFICATION_FACTS[:3]}),
    _case("bidi-d-002", "报价超过预算上限会怎样处理？",
          ("evaluation-method#disqualification",),
          ("投标报价超过招标预算上限 5800 万元的，评标委员会应当否决其投标。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[0]]}),
    _case("bidi-d-003", "投标文件缺少完整实施方案会有什么后果？",
          ("evaluation-method#disqualification",),
          ("未提供完整实施方案的应当否决其投标。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[2]]}),
    _case("bidi-d-004", "串通投标会被如何认定？",
          ("evaluation-method#disqualification",),
          ("经认定属于串通投标的应当否决其投标。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[3]]}),
]

# ── 评分办法 ─────────────────────────────────────────────────────────

SCORING_CASES = [
    _case("bidi-s-001", "本项目采用什么评分方式，满分多少分？",
          ("evaluation-method#scoring-method",),
          ("本项目采用综合评分法进行评标，综合评分法满分 100 分。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[3]]}),
    _case("bidi-s-002", "技术部分的评分标准有哪些？",
          ("evaluation-method#scoring-points",),
          ("技术方案 40 分，投标报价 30 分，实施与运维能力 20 分。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[0], SCORING_POINT_FACTS[1], SCORING_POINT_FACTS[2]]}),
    _case("bidi-s-003", "投标报价是如何评分的？",
          ("evaluation-method#scoring-points",),
          ("满足招标文件要求且报价最低的投标报价为评标基准价。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[4]]}),
    _case("bidi-s-004", "得分相同时如何确定排名？",
          ("evaluation-method#tie-breaking",),
          ("得分相同时，按投标报价由低到高确定排名。",)),
]

# ── 招标术语 / 合同条款 ──────────────────────────────────────────────

TERMINOLOGY_CASES = [
    _case("bidi-t-001", "投标保证金是多少？",
          ("tender-notice#bid-bond",),
          ("本项目投标保证金为人民币 50 万元整。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[0]]}),
    _case("bidi-t-002", "什么是实质性响应要求？",
          ("evaluation-method#substantive-response",),
          ("投标文件须对招标文件提出的全部实质性要求和条件作出响应。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[1]]}),
    _case("bidi-t-003", "本项目对系统集成范围有什么要求？",
          ("evaluation-method#substantive-response",),
          ("实质性要求包括资质、系统集成范围、实施工期、服务等级（SLA）等。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[2], TERMINOLOGY_FACTS[4]]}),
    _case("bidi-t-004", "系统需要满足什么等保要求？",
          ("contract-terms#quality-standard",),
          ("并满足等级保护三级（等保三级）测评要求后方可竣工验收。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[3]]}),
    _case("bidi-t-005", "质量保证金的比例是多少？",
          ("contract-terms#payment",),
          ("剩余 5% 作为质量保证金。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[5]]}),
    _case("bidi-t-006", "预付款比例和支付条件是什么？",
          ("contract-terms#payment",),
          ("预付款为合同价款的 30%。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[6]]}),
]

# ── 招标流程 / 时间 ──────────────────────────────────────────────────

PROCESS_CASES = [
    _case("bidi-p-001", "招标文件从哪里获取，什么时候截止？",
          ("tender-notice#bidding-docs", "tender-notice#timeline"),
          ("招标文件在云谷产业园公共资源交易平台在线获取。",)),
    _case("bidi-p-002", "投标截止时间和开标时间是什么时候？",
          ("tender-notice#timeline",),
          ("投标截止时间为 2026 年 9 月 22 日 14 时 00 分。",)),
    _case("bidi-p-003", "投标文件需要准备几份？",
          ("bidder-instructions#bid-preparation",),
          ("投标文件须提交正本一份、副本三份。",)),
    _case("bidi-p-004", "项目的预算金额和招标编号是什么？",
          ("tender-notice#overview",),
          ("项目预算 5800 万元，招标编号 YG-2026-0908。",)),
    _case("bidi-p-005", "工期延误有什么违约责任？",
          ("contract-terms#delivery-period", "contract-terms#penalties"),
          ("每延误一日按合同价款的千分之一支付违约金。",)),
]

ALL_CASES = (
    QUALIFICATION_CASES
    + DISQUALIFICATION_CASES
    + SCORING_CASES
    + TERMINOLOGY_CASES
    + PROCESS_CASES
)
