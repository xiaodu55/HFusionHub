"""plugin-security.yml 里那三个"从诞生起就没绿过"的门（第一百零四批）。

判据全部来自 runner 日志，不是读 workflow 猜的：

- run 38134153670（锁未修）：`vulnerability-scan` 死在第一步 ——
  `pip-audit -r requirements.txt --desc --output … --format json` 自己在有漏洞时退出 1
  （`Found 29 known vulnerabilities in 5 packages`），解析脚本从没被执行过。
- run 38145150133（第一百零三批把锁修干净之后）：同一步打印
  `No known vulnerabilities found` 并退出 0，下一步的解析脚本却报
  `AttributeError: 'str' object has no attribute 'get'` —— pip-audit 的 JSON 顶层是
  `{"dependencies": […]}`，脚本按"顶层是 list"去迭代，迭代到的元素是字符串键。
  ⇒ 这个 job 有两个叠着的缺陷，前一个一直挡着后一个；只修锁不可能让它转绿。
- `sbom-generation`：runner 装的是未钉版的 `cyclonedx-bom 7.5.0`，其 `environment` 子命令
  只认 `--of / --output-format {JSON,XML}`，门里写的是 `--format json`
  ⇒ `error: unrecognized arguments: --format`。
- `license-check`：runner 装的是未钉版的 `pip-licenses 5.5.5`，`-f/--format` 的可选值是
  `plain / plain-vertical / markdown / rst / confluence / html / json / json-license-finder / csv`，
  门里写的是 `--format=table` ⇒ `invalid choice: 'table'`。

三条的同一根因：**写门的人用的 CLI 与 runner 实际装的版本不同源**，而 runner 那侧的
`pip install <tool>` 没有钉版 —— 于是工具一次改名/改旗标，门就永久红（或永久假绿）。
本批按当版本的正确旗标改，并把三个工具钉住；不删 job、不加 `continue-on-error`、
不放宽任何过滤。
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "plugin-security.yml"
GATE = ROOT / "scripts" / "ci" / "vuln_report_gate.py"


def job_steps(name: str) -> dict[str, str]:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return {
        step["name"]: step.get("run", "")
        for step in doc["jobs"][name]["steps"]
        if "run" in step
    }


def run_gate(report: dict | list | None, tmp_path: Path) -> subprocess.CompletedProcess:
    """用与 CI 相同的方式执行 helper：`python <helper> <report.json>`。

    前置断言不能省：`python <不存在的脚本>` 自己就退出 2，而 2 正是"读不出形态"的退出码——
    少了这一行，所有"必须退出 2"的用例会在 helper 缺席时**空转通过**。
    """
    assert GATE.is_file(), f"{GATE} 不存在——退出码断言全部无意义"
    path = tmp_path / "vuln-report.json"
    if report is not None:
        path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(GATE), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestVulnReportGateSemantics:
    """helper 的退出码契约：0 无漏洞 / 1 有漏洞 / 2 读不出形态，绝不把"读不出"当 0。"""

    def test_clean_report_from_pip_audit_shape_passes(self, tmp_path):
        result = run_gate(
            {
                "dependencies": [
                    {"name": "anyio", "version": "4.14.2", "vulns": []},
                    {"name": "starlette", "version": "1.3.1", "vulns": []},
                ]
            },
            tmp_path,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No known vulnerabilities found" in result.stdout

    def test_one_vulnerability_fails_and_names_id_package_version(self, tmp_path):
        result = run_gate(
            {
                "dependencies": [
                    {
                        "name": "pypdf",
                        "version": "6.16.2",
                        "vulns": [{"id": "GHSA-4m4v-rc76-v3v3", "severity": "high"}],
                    }
                ]
            },
            tmp_path,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "GHSA-4m4v-rc76-v3v3: pypdf==6.16.2" in result.stdout

    def test_low_severity_also_fails_because_there_is_no_filter(self, tmp_path):
        """门名叫 critical/high，实际历来不过滤。钉住"不过滤"，防止未来有人借改旗标放宽门。"""
        result = run_gate(
            {
                "dependencies": [
                    {"name": "requests", "version": "2.31.0", "vulns": [{"id": "GHSA-low", "severity": "low"}]}
                ]
            },
            tmp_path,
        )
        assert result.returncode == 1, result.stdout + result.stderr

    def test_bare_list_shape_is_not_silently_accepted(self, tmp_path):
        """旧形态（顶层 list）现在不再受支持时**必须报错**，不能被当成"零漏洞"。"""
        result = run_gate([{"name": "pypdf", "version": "6.16.2", "vulns": []}], tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "shape" in (result.stdout + result.stderr).lower()

    def test_dict_without_dependencies_is_a_failure_not_a_pass(self, tmp_path):
        result = run_gate({"foo": []}, tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_empty_dependency_list_is_not_a_pass(self, tmp_path):
        """`{"dependencies": []}` ＝ 什么都没审。当成"干净"就是一条空转的绿门。"""
        result = run_gate({"dependencies": []}, tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_malformed_entry_is_a_failure(self, tmp_path):
        result = run_gate({"dependencies": [{"name": "x", "version": "1.0"}]}, tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_missing_file_is_a_failure(self, tmp_path):
        result = run_gate(None, tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_alias_duplicated_ids_are_counted_once_per_package(self, tmp_path):
        """同一公告的别名在 OSV 表里会重复出现——计数按条目，不得按公告去重后少报。"""
        result = run_gate(
            {
                "dependencies": [
                    {
                        "name": "pytest",
                        "version": "8.3.5",
                        "vulns": [{"id": "PYSEC-2026-1845"}, {"id": "GHSA-xxx-pytest"}],
                    }
                ]
            },
            tmp_path,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Found 2 vulnerabilities" in result.stdout


class TestPluginSecurityWorkflowUsesCorrectFlags:
    def test_vulnerability_step_delegates_to_the_helper(self):
        steps = job_steps("vulnerability-scan")
        body = steps["Check for critical/high vulnerabilities"]
        assert "vuln_report_gate.py" in body, body
        assert "python -c" not in body, "解析逻辑必须住在 helper 里，才谈得上被测试执行"

    def test_every_tool_that_gets_flags_is_version_pinned(self):
        """三条门的根因就是未钉版：装了 7.5.0 却按 4.x 的旗标写命令。"""
        text = WORKFLOW.read_text(encoding="utf-8")
        for tool in ("pip-audit", "cyclonedx-bom", "pip-licenses"):
            assert f"{tool}==" in text, f"{tool} 没有钉版"

    def test_sbom_step_uses_output_format_not_the_removed_flag(self):
        body = job_steps("sbom-generation")["Generate SBOM"]
        assert "--format json" not in body, body
        assert "--output-format JSON" in body, body

    def test_license_step_uses_a_real_format_style(self):
        body = job_steps("license-check")["Check licenses"]
        assert "--format=table" not in body, body
        assert "--format=plain" in body, body

    def test_the_three_jobs_are_not_silenced(self):
        """放宽门的三条退路全部钉死：不删步骤、不加 continue-on-error、不 skip。

        `if: always()` 只允许出现在 upload-artifact 步骤上——那是在门已经判红之后
        仍把报告留档，不改变门的结论；出现在任何执行步骤上就是把门静音。
        """
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        for job in ("vulnerability-scan", "sbom-generation", "license-check"):
            for step in doc["jobs"][job]["steps"]:
                assert not step.get("continue-on-error"), f"{job}/{step.get('name')} 被静音了"
                if step.get("uses", "").startswith("actions/upload-artifact"):
                    continue
                assert step.get("if") not in ("always()", "failure()"), f"{job}/{step.get('name')} 被条件跳过"
