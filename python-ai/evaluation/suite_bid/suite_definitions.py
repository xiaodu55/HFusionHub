#!/usr/bin/env python
"""Ground-truth definitions for the 招投标领域评测套件 (B2 垂直化).

对应合成知识库 ``evaluation/kb_bid``（滨海园区虚构招标文件，脱敏）。用例
覆盖四类领域指标（经 ``bid_facts`` 透传，评测时在检索命中内容中做确定性子串
匹配，无需 LLM）：

- ``qualification_recall``          资质要求召回
- ``disqualification_clause_recall`` 废标条款召回
- ``scoring_point_accuracy``         评分点命中
- ``bid_terminology_accuracy``       招标术语命中

``build_suite.py`` 校验每个引用对应 kb_manifest 中真实章节，并冻结
``cases.jsonl`` + ``suite_manifest.json``。
"""

from __future__ import annotations

KB_ID = 201

DOC_TITLES = {
    "tender-notice": "滨海园区智能化改造项目招标公告",
    "bidder-instructions": "投标人须知",
    "evaluation-method": "评标办法",
    "contract-terms": "合同主要条款",
}

# 领域指标维度的期望事实（子串须与语料原文一致，评测时做包含匹配）
QUALIFICATION_FACTS = [
    "建筑智能化工程专业承包资质二级以上",
    "安全生产许可证",
    "项目负责人须具备机电工程专业注册建造师一级执业资格",
    "资产负债率不得高于 85%",
    "至少两项单项合同金额不低于 500 万元",
]
DISQUALIFICATION_FACTS = [
    "投标报价超过招标预算上限 1260 万元",
    "未按招标文件要求密封",
    "未按要求提供投标保证金",
    "不具备招标文件要求的资质条件或业绩要求",
    "属于串通投标",
]
SCORING_POINT_FACTS = [
    "施工组织设计方案 30 分",
    "投标报价 25 分",
    "综合评分法满分 100 分",
    "低价优先法",
]
TERMINOLOGY_FACTS = [
    "投标保证金",
    "实质性响应",
    "评标基准价",
    "投标有效期",
    "竣工验收合格",
    "质量保证金",
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
    _case("bid-q-001", "投标人需要具备什么资质才能参加本项目投标？",
          ("bidder-instructions#qualifications",),
          ("投标人须具备建筑智能化工程专业承包资质二级以上。",),
          {"qualification_recall": QUALIFICATION_FACTS[:3]}),
    _case("bid-q-002", "项目负责人有什么执业资格要求？",
          ("bidder-instructions#qualifications",),
          ("项目负责人须具备机电工程专业注册建造师一级执业资格。",),
          {"qualification_recall": [QUALIFICATION_FACTS[2]]}),
    _case("bid-q-003", "投标人的财务要求是什么，资产负债率有什么限制？",
          ("bidder-instructions#financial",),
          ("投标人资产负债率不得高于 85%。",),
          {"qualification_recall": [QUALIFICATION_FACTS[3]]}),
    _case("bid-q-004", "近三年业绩要求是什么？",
          ("bidder-instructions#performance",),
          ("至少两项单项合同金额不低于 500 万元的建筑智能化工程项目业绩。",),
          {"qualification_recall": [QUALIFICATION_FACTS[4]]}),
    _case("bid-q-005", "招标公告中投标人需要具备哪些资格条件？",
          ("tender-notice#eligibility", "bidder-instructions#qualifications"),
          ("须具备建筑智能化工程专业承包资质二级及以上。",),
          {"qualification_recall": [QUALIFICATION_FACTS[0]]}),
]

# ── 废标条款 ─────────────────────────────────────────────────────────

DISQUALIFICATION_CASES = [
    _case("bid-d-001", "哪些情况会导致废标？",
          ("evaluation-method#disqualification",),
          ("投标报价超过招标预算上限的应当否决其投标。",),
          {"disqualification_clause_recall": DISQUALIFICATION_FACTS[:3]}),
    _case("bid-d-002", "报价超过预算上限会怎样处理？",
          ("evaluation-method#disqualification",),
          ("投标报价超过招标预算上限 1260 万元的，评标委员会应当否决其投标。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[0]]}),
    _case("bid-d-003", "投标文件密封不符合要求会有什么后果？",
          ("bidder-instructions#seal-requirements", "evaluation-method#disqualification"),
          ("未按要求密封、签署的投标文件将被拒收。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[1]]}),
    _case("bid-d-004", "串通投标会被如何认定？",
          ("evaluation-method#disqualification",),
          ("投标文件存在明显雷同，经认定属于串通投标的应当否决。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[4]]}),
]

# ── 评分办法 ─────────────────────────────────────────────────────────

SCORING_CASES = [
    _case("bid-s-001", "本项目采用什么评分方式，满分多少分？",
          ("evaluation-method#scoring-method",),
          ("本项目采用综合评分法进行评标，综合评分法满分 100 分。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[2]]}),
    _case("bid-s-002", "技术部分的评分标准有哪些？",
          ("evaluation-method#scoring-points",),
          ("施工组织设计方案 30 分、技术实施方案 20 分。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[0]]}),
    _case("bid-s-003", "投标报价是如何评分的？",
          ("evaluation-method#scoring-points",),
          ("商务部分投标报价 25 分，采用低价优先法。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[1], SCORING_POINT_FACTS[3]]}),
    _case("bid-s-004", "得分相同时如何确定排名？",
          ("evaluation-method#tie-breaking",),
          ("得分相同按投标报价由低到高确定排名。",)),
]

# ── 招标术语 / 合同条款 ──────────────────────────────────────────────

TERMINOLOGY_CASES = [
    _case("bid-t-001", "投标保证金是多少，什么时候退还？",
          ("tender-notice#bid-bond",),
          ("本项目投标保证金为人民币 20 万元整。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[0]]}),
    _case("bid-t-002", "什么是实质性响应要求？",
          ("evaluation-method#substantive-response",),
          ("投标文件须对招标文件提出的全部实质性要求和条件作出响应。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[1]]}),
    _case("bid-t-003", "评标基准价是如何确定的？",
          ("evaluation-method#scoring-points",),
          ("满足招标文件要求且报价最低的投标报价为评标基准价。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[2]]}),
    _case("bid-t-004", "投标有效期有什么规定？",
          ("bidder-instructions#qualifications",),
          ("资质证书、安全生产许可证须在投标有效期内。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[3]]}),
    _case("bid-t-005", "质量保证金的比例是多少？",
          ("contract-terms#payment",),
          ("剩余 3% 作为质量保证金。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[5]]}),
    _case("bid-t-006", "合同要求的工期是多少天？",
          ("contract-terms#delivery-period",),
          ("本项目工期为 180 日历天。",)),
    _case("bid-t-007", "工程的质量标准是什么？",
          ("contract-terms#quality-standard",),
          ("工程质量标准须符合国家现行工程施工质量验收规范。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[4]]}),
    _case("bid-t-008", "预付款比例和支付条件是什么？",
          ("contract-terms#payment",),
          ("预付款为合同价款的 30%。",)),
    _case("bid-t-009", "质保期内故障响应时间有什么要求？",
          ("contract-terms#warranty",),
          ("接到故障报修后 2 小时内响应。",)),
]

# ── 招标流程 / 时间 ──────────────────────────────────────────────────

PROCESS_CASES = [
    _case("bid-p-001", "招标文件从哪里获取，什么时候截止？",
          ("tender-notice#bidding-docs",),
          ("在滨海市公共资源交易中心网上下载。",)),
    _case("bid-p-002", "投标截止时间和开标时间是什么时候？",
          ("tender-notice#timeline",),
          ("投标截止时间为 2026 年 7 月 15 日 09 时 30 分。",)),
    _case("bid-p-003", "投标文件需要准备几份？",
          ("bidder-instructions#bid-preparation",),
          ("投标文件正本一份、副本四份。",)),
    _case("bid-p-004", "项目的预算金额和招标编号是什么？",
          ("tender-notice#overview",),
          ("项目预算 1260 万元，招标编号 BH-2026-0618。",)),
    _case("bid-p-005", "工期延误有什么违约责任？",
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
