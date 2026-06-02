#!/usr/bin/env python
"""Ground-truth definitions for 工程施工 (construction) 行业方案包评测套件 (P2-4).

对应合成知识库 ``evaluation/kb_bid_construction``（蓉城市政道路提升改造工程，
虚构脱敏）。用例覆盖四类领域指标（经 ``bid_facts`` 透传，评测时在检索命中
内容中做确定性子串匹配，无需 LLM），作为「工程施工行业方案包」售卖的离线质量凭证。

``build_suite.py`` 校验每个引用对应 kb_manifest 中真实章节，并冻结
``cases.jsonl`` + ``suite_manifest.json``。
"""

from __future__ import annotations

KB_ID = 202

DOC_TITLES = {
    "tender-notice": "蓉城市政道路提升改造工程招标公告",
    "bidder-instructions": "投标人须知",
    "evaluation-method": "评标办法",
    "contract-terms": "合同主要条款",
}

# 领域指标维度的期望事实（子串须与语料原文一致，评测时做包含匹配）
QUALIFICATION_FACTS = [
    "市政公用工程施工总承包二级及以上",
    "安全生产许可证",
    "市政公用工程专业一级注册建造师",
    "资产负债率不得高于 80%",
    "单项合同金额不低于 3000 万元",
]
DISQUALIFICATION_FACTS = [
    "投标报价超过招标预算上限 8600 万元",
    "未按要求提供投标保证金",
    "未按要求密封、签署",
    "串通投标",
    "不具备招标文件要求的资质条件",
]
SCORING_POINT_FACTS = [
    "施工组织设计 35 分",
    "投标报价 30 分",
    "综合评分法满分 100 分",
    "评标基准价",
]
TERMINOLOGY_FACTS = [
    "投标保证金",
    "实质性响应",
    "投标有效期",
    "评标基准价",
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
    _case("bidc-q-001", "投标人需要具备什么资质才能参加本项目投标？",
          ("bidder-instructions#qualifications",),
          ("投标人须具备市政公用工程施工总承包二级及以上资质，并持有有效的安全生产许可证。",),
          {"qualification_recall": QUALIFICATION_FACTS[:2]}),
    _case("bidc-q-002", "项目负责人有什么执业资格要求？",
          ("bidder-instructions#qualifications",),
          ("拟派项目负责人须具备市政公用工程专业一级注册建造师执业资格。",),
          {"qualification_recall": [QUALIFICATION_FACTS[2]]}),
    _case("bidc-q-003", "投标人的财务要求是什么，资产负债率有什么限制？",
          ("bidder-instructions#financial",),
          ("投标人近三年财务状况良好，资产负债率不得高于 80%。",),
          {"qualification_recall": [QUALIFICATION_FACTS[3]]}),
    _case("bidc-q-004", "近五年业绩要求是什么？",
          ("bidder-instructions#performance",),
          ("至少完成两项单项合同金额不低于 3000 万元的市政道路类工程项目业绩。",),
          {"qualification_recall": [QUALIFICATION_FACTS[4]]}),
    _case("bidc-q-005", "招标公告中投标人需要具备哪些资格条件？",
          ("tender-notice#eligibility", "bidder-instructions#qualifications"),
          ("投标人须具备市政公用工程施工总承包二级及以上资质。",),
          {"qualification_recall": [QUALIFICATION_FACTS[0]]}),
]

# ── 废标条款 ─────────────────────────────────────────────────────────

DISQUALIFICATION_CASES = [
    _case("bidc-d-001", "哪些情况会导致废标？",
          ("evaluation-method#disqualification",),
          ("投标报价超过招标预算上限的应当否决其投标。",),
          {"disqualification_clause_recall": DISQUALIFICATION_FACTS[:3]}),
    _case("bidc-d-002", "报价超过预算上限会怎样处理？",
          ("evaluation-method#disqualification",),
          ("投标报价超过招标预算上限 8600 万元的，评标委员会应当否决其投标。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[0]]}),
    _case("bidc-d-003", "投标文件密封不符合要求会有什么后果？",
          ("bidder-instructions#seal-requirements", "evaluation-method#disqualification"),
          ("未按要求密封、签署的投标文件将被拒收。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[2]]}),
    _case("bidc-d-004", "串通投标会被如何认定？",
          ("evaluation-method#disqualification",),
          ("经认定属于串通投标的应当否决其投标。",),
          {"disqualification_clause_recall": [DISQUALIFICATION_FACTS[3]]}),
]

# ── 评分办法 ─────────────────────────────────────────────────────────

SCORING_CASES = [
    _case("bidc-s-001", "本项目采用什么评分方式，满分多少分？",
          ("evaluation-method#scoring-method",),
          ("本项目采用综合评分法进行评标，综合评分法满分 100 分。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[2]]}),
    _case("bidc-s-002", "技术部分的评分标准有哪些？",
          ("evaluation-method#scoring-points",),
          ("施工组织设计 35 分，投标报价 30 分。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[0], SCORING_POINT_FACTS[1]]}),
    _case("bidc-s-003", "投标报价是如何评分的？",
          ("evaluation-method#scoring-points",),
          ("满足招标文件要求且报价最低的投标报价为评标基准价。",),
          {"scoring_point_accuracy": [SCORING_POINT_FACTS[3]]}),
    _case("bidc-s-004", "得分相同时如何确定排名？",
          ("evaluation-method#tie-breaking",),
          ("得分相同时，按投标报价由低到高确定排名。",)),
]

# ── 招标术语 / 合同条款 ──────────────────────────────────────────────

TERMINOLOGY_CASES = [
    _case("bidc-t-001", "投标保证金是多少？",
          ("tender-notice#bid-bond",),
          ("本项目投标保证金为人民币 80 万元整。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[0]]}),
    _case("bidc-t-002", "什么是实质性响应要求？",
          ("evaluation-method#substantive-response",),
          ("投标文件须对招标文件提出的全部实质性要求和条件作出响应。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[1]]}),
    _case("bidc-t-003", "评标基准价是如何确定的？",
          ("evaluation-method#scoring-points",),
          ("满足招标文件要求且报价最低的投标报价为评标基准价。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[3]]}),
    _case("bidc-t-004", "投标有效期有什么规定？",
          ("bidder-instructions#qualifications",),
          ("资质证书、安全生产许可证须在投标有效期内。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[2]]}),
    _case("bidc-t-005", "质量保证金的比例是多少？",
          ("contract-terms#payment",),
          ("剩余 3% 作为质量保证金。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[4]]}),
    _case("bidc-t-006", "预付款比例和支付条件是什么？",
          ("contract-terms#payment",),
          ("预付款为合同价款的 30%。",),
          {"bid_terminology_accuracy": [TERMINOLOGY_FACTS[5]]}),
]

# ── 招标流程 / 时间 ──────────────────────────────────────────────────

PROCESS_CASES = [
    _case("bidc-p-001", "招标文件从哪里获取，什么时候截止？",
          ("tender-notice#bidding-docs", "tender-notice#timeline"),
          ("招标文件在蓉城市公共资源交易中心网上下载。",)),
    _case("bidc-p-002", "投标截止时间和开标时间是什么时候？",
          ("tender-notice#timeline",),
          ("投标截止时间为 2026 年 8 月 18 日 09 时 00 分。",)),
    _case("bidc-p-003", "投标文件需要准备几份？",
          ("bidder-instructions#bid-preparation",),
          ("投标文件须提交正本一份、副本四份。",)),
    _case("bidc-p-004", "项目的预算金额和招标编号是什么？",
          ("tender-notice#overview",),
          ("项目预算 8600 万元，招标编号 CJ-2026-0721。",)),
    _case("bidc-p-005", "工期延误有什么违约责任？",
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
