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
- `sbom-generation`：runner 装的是未钉版的 `cyclonedx-bom`（当时解析到 7.5.0），其
  `environment` 子命令只认 `--of / --output-format {JSON,XML}`，门里写的是 `--format json`
  ⇒ `error: unrecognized arguments: --format`。
  钉版没有钉成 7.5.0 而是 `python-ai/requirements-dev.txt` 里已有的 **7.3.1**：实测两版的
  旗标表一致，而钉成 7.5.0 会让同一个仓里并存两个 cyclonedx-bom 版本（eval-nightly 从
  requirements-dev 装的就是 7.3.1，run 38224268851 的日志可查）。
- `license-check`：runner 装的是未钉版的 `pip-licenses 5.5.5`，`-f/--format` 的可选值是
  `plain / plain-vertical / markdown / rst / confluence / html / json / json-license-finder / csv`，
  门里写的是 `--format=table` ⇒ `invalid choice: 'table'`。

三条的同一根因：**写门的人用的 CLI 与 runner 实际装的版本不同源**，而 runner 那侧的
`pip install <tool>` 没有钉版 —— 于是工具一次改名/改旗标，门就永久红（或永久假绿）。
本批按当版本的正确旗标改，并把三个工具钉住；不删 job、不加 `continue-on-error`、
不放宽任何过滤。

第一百零四批同时登记了第四条未处置的错位（`docs/CLEANUP_BACKLOG.md`，第一百一十四批处置）：
`sbom-generation` 那个 job **全程没装过产品依赖**，`cyclonedx-py environment` 读的是当前
解释器已装的包，于是产物描述的是 runner 的环境而不是产品的依赖面。判据来自 push `779fd23b`
那条 run 38332373261 的产物本体（`gh run download -n sbom`，本批解过）：

- 组件 **35** 个 ＝ `cyclonedx-bom 7.3.1` 的闭包 ＋ `pip`；
- `python-ai/requirements.txt` 的顶层 pin 是 **78** 个，ubuntu 侧按 marker 适用的是 **76** 个
  （`pywin32` / `win32-setctime` 带 `sys_platform == "win32"`，runner 上装不到）；
- 拿本批的门对那份真产物回放：**42 个缺失**（`fastapi`、`uvicorn`、`httpx`、`numpy`、
  `pandas`、`pymilvus`、`pypdf` ……）**＋ 9 个版本与锁不符**（`lxml`、`packaging`、`rpds-py`、
  `setuptools`、`tzdata`、`fqdn`、`idna`、`jsonpointer`、`pyparsing`）—— 后者的原因是那批包
  由 cyclonedx-bom 现拉最新版本，不是锁钉的那一版。
  ⇒ "SBOM 是供应链凭证"这句话当时不成立：它既没覆盖产品依赖面，也没记锁的版本。

改法沿用同流水线 `license-check` 已验证的形状：那个 job 的 `Check licenses` 步骤里有
`pip install -r requirements.txt`，同一条 run 的日志 `:345` 打印
`Successfully installed annotated-doc-0.0.5 … websockets-16.1.1`（76 个包，01:29:42→01:31:23
≈ 90 秒），且里面**没有** `pywin32` / `win32-setctime` —— 这两条带
`sys_platform == "win32"`，在 ubuntu runner 上按 marker 跳过。⇒ "先装锁再生成"在这个 runner
上是实测可跑通的，而一致性判定必须按 marker 算适用面，否则那两条 win32-only 的 pin 会让门
**天生红**（这与第八十八批给锁补 marker 是同一条因果）。
组件表为空从 `print('WARNING: …')` 改成非 0 退出，判据住在
`scripts/ci/sbom_lock_coverage_gate.py` 里被下面的测试直接执行 —— 内联在 YAML 里的 `python -c`
没法被测试跑到，那正是第一百零四批那条 `AttributeError` 能藏两批的原因。
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "plugin-security.yml"
GATE = ROOT / "scripts" / "ci" / "vuln_report_gate.py"
SBOM_GATE = ROOT / "scripts" / "ci" / "sbom_lock_coverage_gate.py"
LOCK = ROOT / "python-ai" / "requirements.txt"
DEV_LOCK = ROOT / "python-ai" / "requirements-dev.txt"


def dev_lock_version(tool: str) -> str | None:
    """requirements-dev.txt 里该工具的钉版（行形如 `cyclonedx-bom==7.3.1 \\` + hash 续行）。"""
    pattern = re.compile(rf"^{re.escape(tool)}==([0-9][^ ;\\]*)")
    for line in DEV_LOCK.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1)
    return None


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

    def test_pins_that_the_dev_lock_already_carries_agree_with_it(self):
        """同一个仓里同一个工具只能有一个版本——钉版的来源必须是锁。

        第一百零四批自己踩过这一条：把 sbom 工具钉成"未钉版当时解析到的 7.5.0"，而
        `python-ai/requirements-dev.txt` 早就钉着 7.3.1，eval-nightly 从锁装的就是 7.3.1。
        于是 plugin-security 与 eval-nightly 跑的不是同一个 cyclonedx-bom —— 门仍然各自绿，
        但"同一个工具"这句话已经不成立。这条测试钉的是版本号的**来源**，不钉任何具体版本。
        """
        text = WORKFLOW.read_text(encoding="utf-8")
        compared = []
        for tool, pinned in re.findall(r"pip install ([\w][\w.-]*)==(\S+)", text):
            locked = dev_lock_version(tool)
            if locked is None:
                continue
            compared.append(tool)
            assert pinned == locked, f"{tool}: workflow 钉 {pinned}，requirements-dev.txt 钉 {locked}"
        assert compared, "没有任何钉版能与锁对照——这条测试已经空转"

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


def run_sbom_gate(
    sbom: dict | None,
    lock_text: str,
    tmp_path: Path,
    sys_platform: str = "linux",
    raw_sbom: str | None = None,
) -> subprocess.CompletedProcess:
    """用与 CI 相同的方式执行 SBOM 门：`python <helper> <sbom.json> <requirements.txt>`。

    `sys_platform` 一定显式传：不传时 helper 按**当前宿主**算 marker 适用面，那会让同一份
    fixture 在 Windows 开发和 ubuntu CI 上得出不同结论——门的语义不能跟着环境漂。同一件事
    在第八十八批出现过另一面：锁里缺 `sys_platform` marker 时，Windows 上编译出的锁描述的
    就不是同一份依赖面。
    """
    assert SBOM_GATE.is_file(), f"{SBOM_GATE} 不存在——退出码断言全部无意义"
    sbom_path = tmp_path / "sbom.json"
    if raw_sbom is not None:
        sbom_path.write_text(raw_sbom, encoding="utf-8")
    elif sbom is not None:
        sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
    lock_path = tmp_path / "requirements.txt"
    lock_path.write_text(lock_text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SBOM_GATE), str(sbom_path), str(lock_path), "--sys-platform", sys_platform],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def sbom_of(pairs: dict[str, str]) -> dict:
    return {"components": [{"name": name, "version": version} for name, version in pairs.items()]}


# 独立 oracle：只认列 0 的 `name[extras]==version`，带 `--hash=` 续行、`# via` 注释和
# `--index-url` 选项行。测试自己解析一遍再与 helper 对照，避免"用被测代码的输出构造输入"
# 这种自证。marker 的适用面按字面判断——本仓的锁里只有 `== "win32"` / `!= "win32"` 两种形态。
_LOCK_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([^ ;\\]+)")


def oracle_pins(text: str, sys_platform: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0] in " #-":
            continue
        if sys_platform != "win32" and 'sys_platform == "win32"' in line:
            continue
        if sys_platform == "win32" and 'sys_platform != "win32"' in line:
            continue
        match = _LOCK_PIN_RE.match(line)
        if match:
            pins[match.group(1)] = match.group(2)
    return pins


class TestSbomLockCoverageGateSemantics:
    """helper 的退出码契约：0 覆盖齐 / 1 缺件或版本不符 / 2 读不出对象。

    和 `vuln_report_gate.py` 同一条纪律：**读不出不能当 0**。第一百零四批那条
    `WARNING: SBOM has no components` 就是"读不出当绿"的实例——组件表空到门也只打印，
    于是产物描述 35 个 runner 组件这件事在 CI 里没有任何地方会红。
    """

    def test_full_coverage_passes(self, tmp_path):
        result = run_sbom_gate(
            sbom_of({"fastapi": "0.141.1", "httpx": "0.28.1"}),
            "fastapi==0.141.1 \\\n    --hash=sha256:aa\nhttpx==0.28.1\n",
            tmp_path,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "2" in result.stdout, result.stdout

    def test_missing_package_fails_and_names_it(self, tmp_path):
        result = run_sbom_gate(
            sbom_of({"fastapi": "0.141.1"}),
            "fastapi==0.141.1\nhttpx==0.28.1\n",
            tmp_path,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "httpx" in result.stdout

    def test_version_mismatch_fails_and_shows_both_sides(self, tmp_path):
        """锁钉 lxml==6.1.1、产物里是别的版本 —— 正是 runner 实测的 9 条之一那种错位。"""
        result = run_sbom_gate(
            sbom_of({"lxml": "5.0.0"}),
            "lxml==6.1.1\n",
            tmp_path,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "6.1.1" in result.stdout and "5.0.0" in result.stdout

    def test_empty_components_is_a_failure_not_a_warning(self, tmp_path):
        """本批的核心一条：空组件表过去只 print('WARNING: …')，退出码仍是 0。"""
        result = run_sbom_gate({"components": []}, "fastapi==0.141.1\n", tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "WARNING: SBOM has no components" not in result.stdout

    def test_missing_sbom_file_is_a_failure(self, tmp_path):
        result = run_sbom_gate(None, "fastapi==0.141.1\n", tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_unparseable_sbom_is_a_failure(self, tmp_path):
        result = run_sbom_gate(None, "fastapi==0.141.1\n", tmp_path, raw_sbom="{not json")
        assert result.returncode == 2, result.stdout + result.stderr

    def test_sbom_without_a_components_list_is_a_failure(self, tmp_path):
        result = run_sbom_gate({"foo": []}, "fastapi==0.141.1\n", tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_lock_line_without_a_pin_is_a_failure(self, tmp_path):
        """锁里出现未钉版的一行 ＝ 读不出要描述的对象，不能"跳过它继续判剩下的"。"""
        result = run_sbom_gate(sbom_of({"fastapi": "0.141.1"}), "fastapi==0.141.1\nuvicorn\n", tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr

    def test_names_are_matched_canonically(self, tmp_path):
        """PEP 503 归一：`Boolean.Py` / `boolean_py` / `boolean-py` 是同一个分发名。"""
        result = run_sbom_gate(
            sbom_of({"Boolean.Py": "5.0", "typing_extensions": "4.16.0"}),
            "boolean-py==5.0\ntyping-extensions==4.16.0\n",
            tmp_path,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_extras_do_not_change_the_component_name(self, tmp_path):
        result = run_sbom_gate(
            sbom_of({"uvicorn": "0.27.0"}),
            "uvicorn[standard]==0.27.0\n",
            tmp_path,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_zero_applicable_pins_is_a_failure_not_a_pass(self, tmp_path):
        """锁里全是别的平台的包 ⇒ 这一侧的适用面为空。当成"覆盖良好"就是一条空转的绿门。"""
        result = run_sbom_gate(
            {"components": []},
            'pywin32==312 ; sys_platform == "win32"\n',
            tmp_path,
            sys_platform="linux",
        )
        assert result.returncode == 2, result.stdout + result.stderr

    def test_win32_only_pins_are_required_only_on_win32(self, tmp_path):
        """适用面必须由 marker 决定：ubuntu runner 上装不到 pywin32，门不能天生红。"""
        lock = 'pywin32==312 ; sys_platform == "win32"\nuvicorn==0.27.0\n'
        linux = run_sbom_gate(sbom_of({"uvicorn": "0.27.0"}), lock, tmp_path, sys_platform="linux")
        assert linux.returncode == 0, linux.stdout + linux.stderr
        on_win = run_sbom_gate(sbom_of({"uvicorn": "0.27.0"}), lock, tmp_path, sys_platform="win32")
        assert on_win.returncode == 1, on_win.stdout + on_win.stderr
        assert "pywin32" in on_win.stdout


class TestSbomGenerationDescribesTheProductSurface:
    """`sbom-generation` 的产物必须描述 `requirements.txt`，否则它不是供应链凭证。"""

    def test_sbom_step_installs_the_lock_before_generating(self):
        body = job_steps("sbom-generation")["Generate SBOM"]
        install = body.find("pip install -r requirements.txt")
        generate = body.find("cyclonedx-py environment")
        assert install != -1, f"没先装产品依赖，environment 读的是 runner 环境：{body}"
        assert generate != -1, body
        assert install < generate, "必须先装锁再生成——顺序反了产物仍是安装前的环境"

    def test_coverage_is_judged_by_the_helper_not_inline_python(self):
        body = job_steps("sbom-generation")["Generate SBOM"]
        assert "sbom_lock_coverage_gate.py" in body, body
        assert "python -c" not in body, "解析逻辑必须住在 helper 里，才谈得上被测试执行"

    def test_gate_receives_both_the_artifact_and_the_lock(self):
        """只把 SBOM 递给门，等于让它"数一下组件"——78 个 pin 那条对照就没了。"""
        body = job_steps("sbom-generation")["Generate SBOM"]
        line = next((row for row in body.splitlines() if "sbom_lock_coverage_gate.py" in row), "")
        assert "sbom-python.json" in line, line
        assert "requirements.txt" in line, line

    def test_the_real_lock_is_covered_on_the_ci_platform(self, tmp_path):
        """拿仓库真锁跑一次：helper 的解析必须与测试侧独立 oracle 的结论一致。

        这条是"门在真数据上会咬"的证据，而不是只在 fixture 上自洽。fixture 用 oracle 从锁
        现场造，所以锁以后加包不需要改测试——但锁若出现 helper 认不出的行形，这里会红。
        """
        text = LOCK.read_text(encoding="utf-8")
        pins = oracle_pins(text, "linux")
        assert len(pins) > 50, f"独立 oracle 只解析出 {len(pins)} 个 pin，这条测试已经空转"
        result = run_sbom_gate(sbom_of(pins), text, tmp_path, sys_platform="linux")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_applicability_floor_tracks_the_lock_not_a_hardcoded_name_set(self, tmp_path):
        """同一份产物换个平台就得判红：适用面是算出来的，不是写死的名单。"""
        text = LOCK.read_text(encoding="utf-8")
        win_only = set()
        for line in text.splitlines():
            if line[:1] in ("", " ", "#", "-") or 'sys_platform == "win32"' not in line:
                continue
            match = _LOCK_PIN_RE.match(line)
            if match:
                win_only.add(match.group(1))
        assert win_only, "锁里已经没有 win32-only 的 pin 了——这条测试空转，请先确认适用面还随 marker 变"
        pins = oracle_pins(text, "linux")
        result = run_sbom_gate(sbom_of(pins), text, tmp_path, sys_platform="win32")
        assert result.returncode == 1, result.stdout + result.stderr
        for name in win_only:
            assert name in result.stdout, result.stdout
