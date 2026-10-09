#!/usr/bin/env python3
"""pip-audit JSON 报告的判定门（第一百零四批）。

为什么要从 workflow 的内联 `python -c` 搬出来：那条脚本按"顶层是 list"去迭代报告，
而 pip-audit 现在写的是 `{"dependencies": […]}` —— 迭代 dict 得到的是字符串键，
于是 `AttributeError: 'str' object has no attribute 'get'`。这个缺陷在 runner 上藏了
整整两批：锁没修时先死在 `pip-audit` 自己退出 1（`Found 29 known vulnerabilities…`），
第一百零三批把锁修干净之后才轮到它红（run 38145150133）。内联在 YAML 里的逻辑没法被
测试执行，所以搬进 helper，由 `python-ai/tests/test_plugin_security_gates.py` 直接跑。

退出码契约：
  0 = 报告读得出，且漏洞条数为 0
  1 = 至少一条漏洞。**不按 severity 过滤** —— job 名里的 critical/high 是历史命名，
      它实际的语义一直是"任何一条都判红"，本批不借搬动之机放宽它。
  2 = 报告打不开 / 形态不认识 / 依赖数为 0。这三种都不能当成"干净"：
      把读不出当 0 就是一条永远绿的空转门。
"""

from __future__ import annotations

import json
import sys

USAGE = "usage: vuln_report_gate.py <pip-audit-json-report>"


def _fail(reason: str) -> int:
    print(f"vuln_report_gate: {reason} - cannot read the audit result.", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as handle:
            report = json.load(handle)
    except OSError as exc:
        return _fail(f"report cannot be opened ({exc})")
    except json.JSONDecodeError as exc:
        return _fail(f"report is not valid JSON ({exc})")

    if not isinstance(report, dict) or not isinstance(report.get("dependencies"), list):
        got = type(report).__name__
        keys = sorted(report) if isinstance(report, dict) else []
        return _fail(f"unrecognized report shape: top level {got}, keys {keys}")

    dependencies = report["dependencies"]
    if not dependencies:
        return _fail("unrecognized report shape: zero dependencies audited")

    findings: list[tuple[str, str, str]] = []
    for entry in dependencies:
        if not isinstance(entry, dict):
            return _fail(f"unrecognized report shape: dependency entry is {type(entry).__name__}")
        name = entry.get("name")
        version = entry.get("version")
        vulns = entry.get("vulns")
        if not isinstance(name, str) or not isinstance(version, str) or not isinstance(vulns, list):
            return _fail(f"unrecognized report shape: malformed dependency entry {entry!r:.120}")
        for vuln in vulns:
            if not isinstance(vuln, dict):
                return _fail(f"unrecognized report shape: malformed vulnerability in {name}")
            findings.append((str(vuln.get("id", "")), name, version))

    if findings:
        packages = {name for _, name, _ in findings}
        print(f"Found {len(findings)} vulnerabilities in {len(packages)} packages:")
        for vuln_id, name, version in findings:
            print(f"  {vuln_id}: {name}=={version}")
        return 1

    print(f"No known vulnerabilities found ({len(dependencies)} packages audited)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
