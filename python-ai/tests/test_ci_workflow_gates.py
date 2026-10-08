"""CI 侧两处自伤的判据（第九十批）。

这批修的都不是产品行为，而是 **CI 自己把绿的路走成红的路**：

1. `docker-compose-validate` 的 dev 与 monitoring 两步只喂了部分变量，而
   `docker/docker-compose.yml` 用 `${VAR:?…}` 硬要求 6 个、monitoring 要求 1 个。
   `docker compose config -q` 在第一个缺失变量处就报错 ⇒ 整个 job 红，后面几步从没跑过。
   判据必须**从 compose 文件自己派生**，而不是把变量名抄进测试再抄进 workflow——
   第三处手抄正是这个缺陷能存在至今的原因。
2. `python-container` 的容器门禁在"没有任何 skip"时必然失败：`set -euo pipefail` 下
   `grep '[0-9]+ skipped'` 找不到就返回 1，`pipefail` 让赋值失败，`set -e` 直接打死步骤。
   实测（bash 5.2.37）：输入 `42 passed in 23.65s` ⇒ 退出 1 且根本没走到判断；输入
   `33 passed, 6 skipped in 12.0s` ⇒ 走到判断。也就是说这个 P0 门禁的语义正好反了。
   修法是把计数逻辑放进 `scripts/ci/check_container_skips.sh`，本测试**直接执行它**。
3. 光测 helper 还不够：步骤体自己也会错。`TestContainerGateStepExecution` 把 ci.yml 里那段
   shell 原样落盘、用 `python` 桩喂给它、按 GitHub `shell: bash` 的起手（`--noprofile
   --norc -eo pipefail`）真执行五种形态，断言退出码与注解。本批就是靠它抓到
   PIPESTATUS 被中间赋值重置 ⇒ gate_status 取空 ⇒ 有 skip 也判绿。
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
HELPER = ROOT / "scripts" / "ci" / "check_container_skips.sh"

REQUIRED_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*):\?")
COMPOSE_FILE = re.compile(r"-f\s+(\S+\.ya?ml)")


def required_vars(compose_path: Path) -> set[str]:
    """compose 文件里 `${VAR:?…}` 形式的必填变量。"""
    return set(REQUIRED_VAR.findall(compose_path.read_text(encoding="utf-8")))


def validate_steps() -> dict[str, tuple[Path, set[str]]]:
    """{步骤名: (它校验的 compose 文件, 该步骤 env 提供的变量名集合)}。"""
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    steps = doc["jobs"]["docker-compose-validate"]["steps"]
    found: dict[str, tuple[Path, set[str]]] = {}
    for step in steps:
        run = step.get("run") or ""
        match = COMPOSE_FILE.search(run)
        if not match:
            continue
        found[step["name"]] = (ROOT / match.group(1), set((step.get("env") or {}).keys()))
    return found


class TestComposeValidateEnvPairing:
    def test_three_compose_files_are_validated(self):
        steps = validate_steps()
        files = {path.name for path, _ in steps.values()}
        assert files == {
            "docker-compose.yml",
            "docker-compose.prod.yml",
            "docker-compose.monitoring.yml",
        }, f"validate 步骤覆盖的文件变了：{sorted(steps)}"

    @pytest.mark.parametrize(
        "step_name",
        [
            "Validate dev Docker Compose configuration",
            "Validate production Docker Compose configuration",
            "Validate monitoring Docker Compose configuration",
        ],
    )
    def test_every_required_var_is_supplied(self, step_name: str):
        steps = validate_steps()
        assert step_name in steps, f"workflow 里找不到步骤 {step_name!r}"
        compose_path, supplied = steps[step_name]
        required = required_vars(compose_path)
        assert required, f"{compose_path.name} 里一个必填变量都没有？解析可能失效"
        missing = sorted(required - supplied)
        assert not missing, (
            f"{compose_path.name} 用 ${{VAR:?}} 要求 {sorted(required)}，"
            f"但步骤 {step_name!r} 没提供：{missing} ⇒ `compose config -q` 必然在此报错"
        )

    @pytest.mark.parametrize(
        "step_name",
        [
            "Validate dev Docker Compose configuration",
            "Validate production Docker Compose configuration",
            "Validate monitoring Docker Compose configuration",
        ],
    )
    def test_no_supplied_var_is_unreferenced(self, step_name: str):
        """喂了文件里根本不引用的变量 = 假配置面，与缺变量一样会骗人。"""
        compose_path, supplied = validate_steps()[step_name]
        text = compose_path.read_text(encoding="utf-8")
        dead = sorted(v for v in supplied if f"${{{v}" not in text)
        assert not dead, f"{compose_path.name} 不引用这些变量却被提供：{dead}"


bash = shutil.which("bash")


@pytest.mark.skipif(bash is None, reason="门禁脚本是 POSIX shell，需要 bash 才能真执行")
class TestContainerSkipGate:
    def run_helper(self, stdin_text: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [bash, str(HELPER)],
            input=stdin_text,
            capture_output=True,
            # 宿主默认码页是 GBK：helper 的输出里一旦出现非 ASCII，reader 线程解码失败
            # 会让 proc.stdout 变成 None —— 退出码看着对，判据其实读不到任何东西。
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

    def test_clean_run_with_no_skips_passes(self):
        """这条就是 CI 实际撞上的形态：42 passed、0 skipped 必须判绿。"""
        proc = self.run_helper(".......................................... [100%]\n42 passed in 23.65s\n")
        assert proc.returncode == 0, f"无 skip 的干净跑被判红：stdout={proc.stdout!r} stderr={proc.stderr!r}"

    def test_skipped_tests_fail_the_gate(self):
        proc = self.run_helper("33 passed, 6 skipped in 12.00s\n")
        assert proc.returncode == 1, f"有 6 个 skip 却判绿：{proc.stdout!r}"
        assert "6" in proc.stdout, f"要打印跳过的条数：{proc.stdout!r}"

    def test_only_the_skip_count_is_summed(self):
        """`-rs` 的逐条原因行里也有 '1 skipped'，只能数汇总行，否则重复计数。"""
        proc = self.run_helper(
            "tests/test_x.py::test_a SKIPPED (need docker)\n7 passed, 1 skipped in 3.00s\n"
        )
        assert proc.returncode == 1
        assert "1 skipped" in proc.stdout

    def test_missing_summary_line_is_not_silently_green(self):
        """连汇总行都没有（例如采集阶段就崩）不能当成 0 skipped 放过去。"""
        proc = self.run_helper("no tests ran in 0.01s\n")
        assert proc.returncode == 2, f"没有汇总行时应判'读不到结论'而不是绿：{proc.stdout!r}"

    def test_gate_messages_are_ascii(self):
        """helper 的输出行必须纯 ASCII：本批实测踩过一次——含破折号时 GBK 解码失败，
        `proc.stdout` 静默变成 `None`，退出码正确而判据其实什么都没读到。"""
        for stdin_text in (
            "42 passed in 23.65s\n",
            "33 passed, 6 skipped in 12.00s\n",
            "no tests ran in 0.01s\n",
        ):
            proc = self.run_helper(stdin_text)
            assert proc.stdout.isascii(), f"stdout 含非 ASCII：{proc.stdout!r}"
            assert proc.stderr.isascii(), f"stderr 含非 ASCII：{proc.stderr!r}"

    def test_workflow_step_delegates_to_the_helper(self):
        doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
        steps = doc["jobs"]["python-container"]["steps"]
        gate = next(s for s in steps if "container plugin gates" in (s.get("name") or ""))
        # 把 YAML 里的续行折平成一条逻辑行，否则管道关系看不见
        run = re.sub(r"\\\s*\n\s*", " ", gate["run"])
        # 只认 bash 调用形态：步骤注释里也写着脚本名，光查字符串会漏掉"调用被删了"这种漂移
        assert re.search(r'bash\s+"?\S*scripts/ci/check_container_skips\.sh', run), (
            f"helper 没有被 bash 执行：{run!r}"
        )
        assert "| bash" in run or "|  bash" in run, (
            "helper 必须接住 pytest 的输出（管道），否则它数不到东西"
        )
        assert "grep -oE" not in run, "内联计数管道就是 pipefail 死因，不能再留在 workflow 里"


@pytest.mark.skipif(bash is None, reason="要真执行 workflow 里那段 shell，需要 bash")
class TestContainerGateStepExecution:
    """把 ci.yml 门禁步骤的**本体**抽出来真跑，而不是核对它的文本。

    本批第一次这样跑就抓到步骤自己的缺陷：`pytest_status=${PIPESTATUS[0]}` 与
    `gate_status=${PIPESTATUS[2]}` 分成两条赋值时，第二条读到的 PIPESTATUS 已经是
    第一条赋值自己的状态 ⇒ gate_status 为空 ⇒ `[ … -ne 0 ]` 报
    "integer expression expected"，有 6 条 skip 也照样判绿。文本判据对这种缺陷完全无感。
    """

    @staticmethod
    def step_body() -> str:
        doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
        gate = next(s for s in doc["jobs"]["python-container"]["steps"]
                    if "container plugin gates" in (s.get("name") or ""))
        return gate["run"]

    @staticmethod
    def run_step(tmp_path, output: str, pytest_rc: int) -> subprocess.CompletedProcess:
        shim = tmp_path / "pyshim"
        shim.mkdir()
        # workflow 里写的是 `python -m pytest …`，这里用桩替掉，只喂给门禁一段固定输出
        fake_python = shim / "python"
        fake_python.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$FAKE_PYTEST_OUT\"\nexit \"${FAKE_PYTEST_RC:-0}\"\n",
            encoding="utf-8",
            newline="\n",
        )
        fake_python.chmod(fake_python.stat().st_mode | 0o111)
        # 步骤体必须原样落盘再执行；路径给相对名，避开 msys/windows 两种路径形态的坑
        (tmp_path / "gate_step.sh").write_text(TestContainerGateStepExecution.step_body(),
                                               encoding="utf-8", newline="\n")
        env = {
            **os.environ,
            # 传 "bash" 给 subprocess 会命中 Windows 的 App Execution Alias ⇒ WSL bash
            # （看不见仓库路径），只有 which 给的绝对路径才是 Git/MSYS 的那个 bash。
            "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_WORKSPACE": str(ROOT).replace("\\", "/"),
            "FAKE_PYTEST_OUT": output,
            "FAKE_PYTEST_RC": str(pytest_rc),
        }
        return subprocess.run(
            # 照抄 GitHub `shell: bash` 的起手：--noprofile --norc -eo pipefail
            [bash, "--noprofile", "--norc", "-eo", "pipefail", "gate_step.sh"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )

    @pytest.mark.parametrize(
        ("output", "pytest_rc", "expected"),
        [
            pytest.param("42 passed in 23.65s", 0, 0, id="干净跑_0skip_判绿"),
            pytest.param("33 passed, 6 skipped in 12.00s", 0, 1, id="有skip_判红"),
            pytest.param("1 failed, 41 passed in 23.65s", 1, 1, id="pytest失败_沿用它的退出码"),
            pytest.param("ImportError: cannot import name x", 0, 2, id="读不到汇总行_判红2"),
            pytest.param("INTERNALERROR> boom", 3, 3, id="pytest崩且无汇总行_退出码归pytest"),
        ],
    )
    def test_step_exit_code(self, tmp_path, output: str, pytest_rc: int, expected: int):
        proc = self.run_step(tmp_path, output, pytest_rc)
        assert proc.returncode == expected, (
            f"步骤退出码 {proc.returncode} != {expected}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
        # shell 自己的报错（空变量、语法错）也算失败：一条"跑起来了但全靠运气"的门禁不可信
        assert proc.stderr == "" or "gate_step.sh" not in proc.stderr, (
            f"步骤体自身报错：{proc.stderr!r}"
        )

    def test_skip_count_reaches_the_step_output(self, tmp_path):
        """退出码对了还不够，步骤得把条数说出口——否则运维只能重跑一遍去猜。"""
        proc = self.run_step(tmp_path, "33 passed, 6 skipped in 12.00s", 0)
        assert "6 skipped" in proc.stdout, f"步骤没转达 skip 条数：{proc.stdout!r}"
        assert "::error::" in proc.stdout, f"没有 GitHub 注解：{proc.stdout!r}"


# ═══════════════════════════════════════════════════════════════════════
# 4. 容器轨的归属与守卫的可诊断性（第一百批）
# ═══════════════════════════════════════════════════════════════════════

CONTAINER_LANE_FILE = "tests/test_plugin_container.py"
LANE_SOURCE = ROOT / "python-ai" / "tests" / "test_plugin_container.py"


def job_steps(job: str) -> list[dict]:
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def pytest_runs(job: str) -> list[str]:
    """该 job 里所有含 pytest 的 run 步骤体（反斜杠续行折平成一条逻辑行）。"""
    runs = []
    for step in job_steps(job):
        run = step.get("run") or ""
        if re.search(r"\bpytest\b", run):
            runs.append(re.sub(r"\\s*\n\s*", " ", run))
    return runs


def guard_candidate_tags() -> list[str]:
    """从守卫源码里读它认得的本地基础镜像候选，绝不把标签名抄第三遍。"""
    source = LANE_SOURCE.read_text(encoding="utf-8")
    block = source.split("def _resolve_local_python_image", 1)[1]
    block = block.split("\n    def ", 1)[0] if "\n    def " in block else block
    return re.findall(r'"(python:[^"]+)"', block)


def pulled_image_tags(job: str) -> list[str]:
    tags = []
    for step in job_steps(job):
        run = step.get("run") or ""
        tags.extend(re.findall(r"docker pull\s+([^\s|]+)", run))
    return tags


class TestContainerLaneOwnership:
    """容器轨只能有一个 owner job，且那个 job 预备的镜像必须是守卫认得的标签。

    第九十批留下的形态：`python` job 跑整个 `tests/`（含容器专项），而它既不预置
    Docker 基础镜像也不起 runner ⇒ 6 条 fixture ERROR 永远在；同时
    `python-container` 那侧真的跑了 42 例。两个 job 对同一个文件的期待不一致，
    ERROR 就成了"这个 job 本来就不该跑它"的噪音，把该文件真正的错误一起淹掉。
    """

    def test_python_job_does_not_run_the_container_lane(self):
        runs = pytest_runs("python")
        assert runs, "python job 里找不到 pytest 步骤，判据无从下手"
        for run in runs:
            assert f"--ignore={CONTAINER_LANE_FILE}" in run, (
                f"容器专项仍被无镜像的 python job 执行：{run!r}"
            )

    def test_the_exclusion_is_one_file_not_a_shrunk_suite(self):
        """排除只能针对那一个文件：整个套件与覆盖率棘轮必须原样留着。"""
        run = pytest_runs("python")[0]
        assert re.search(r"pytest\s+-q\s+tests\b", run), f"套件面被缩小：{run!r}"
        assert "--cov=app" in run and "--cov-fail-under" in run, "覆盖率棘轮被顺手删了"
        assert run.count("--ignore") == 1, f"--ignore 出现多次，容器轨之外还有别的排除：{run!r}"

    def test_container_job_owns_the_lane_and_still_gates_skips(self):
        runs = pytest_runs("python-container")
        assert len(runs) == 1, f"容器轨被跑在 {len(runs)} 个步骤里，owner 不唯一"
        assert CONTAINER_LANE_FILE in runs[0], f"owner job 没跑那个文件：{runs[0]!r}"
        assert "check_container_skips.sh" in runs[0], "skip 门禁不再接住容器轨的输出"

    def test_every_image_the_ci_pulls_is_one_the_guard_accepts(self):
        """预拉与检测必须同源：候选表由守卫源码自己给出，不抄第二遍。"""
        candidates = guard_candidate_tags()
        assert candidates, f"读不到守卫的候选表，判据失效：{LANE_SOURCE}"
        pulled = pulled_image_tags("python-container")
        assert pulled, "python-container job 不再准备任何基础镜像 ⇒ 容器轨必然红"
        unknown = [tag for tag in pulled if tag not in candidates]
        assert not unknown, f"预拉了守卫不认得的标签 {unknown}，候选表：{candidates}"


def _resolve_local_python_image():
    from test_plugin_container import TestRunnerIntegration

    return TestRunnerIntegration._resolve_local_python_image


class _FakeImage:
    def __init__(self, tags):
        self.tags = list(tags)


class _FakeImages:
    def __init__(self, tags_per_image=(), error=None):
        self._error = error
        self._images = [_FakeImage(tags) for tags in tags_per_image]

    def list(self):
        if self._error is not None:
            raise self._error
        return self._images


class _FakeClient:
    def __init__(self, images):
        self.images = images


class TestContainerImageGuardDiagnostics:
    """守卫可以一直"缺镜像就 fail"，但必须把**缺镜像**和**问不到 daemon**说成两件事。

    原实现把 `client.images.get()` 与 `client.images.list()` 的异常全部吞掉，最后统一
    fail 成 "Integration tests require a tagged local Python base image"，于是
    daemon 不可达（DOCKER_HOST 错、socket 权限）也被报成"你没拉镜像"——第九十批 CI 日志里
    "预拉步骤过了、测试却说无镜像"的说不通正是这个形态。
    """

    def test_daemon_unreachable_is_reported_as_daemon(self):
        client = _FakeClient(_FakeImages(error=ConnectionError("No such file or directory")))
        with pytest.raises(pytest.fail.Exception) as excinfo:
            _resolve_local_python_image()(client)
        message = str(excinfo.value)
        assert "守护进程" in message, f"daemon 故障被报成了缺镜像：{message!r}"
        assert "tagged local Python base image" not in message

    def test_missing_image_is_still_a_fail_not_a_skip(self):
        client = _FakeClient(_FakeImages(tags_per_image=[("alpine:3.20",)]))
        with pytest.raises(pytest.fail.Exception) as excinfo:
            _resolve_local_python_image()(client)
        message = str(excinfo.value)
        assert "守护进程" not in message, f"daemon 明明可达却报 daemon：{message!r}"
        assert "python:3.12-slim" in message, f"没交代候选表：{message!r}"

    def test_candidate_order_decides_when_several_are_present(self):
        client = _FakeClient(
            _FakeImages(tags_per_image=[("python:3.11-slim",), ("python:3.12-slim",)])
        )
        assert _resolve_local_python_image()(client) == "python:3.12-slim"

    def test_fallback_accepts_any_tagged_python_image(self):
        client = _FakeClient(_FakeImages(tags_per_image=[("python:3.13-slim",)]))
        assert _resolve_local_python_image()(client) == "python:3.13-slim"

    def test_untagged_local_image_is_not_silently_used(self):
        client = _FakeClient(_FakeImages(tags_per_image=[()]))
        with pytest.raises(pytest.fail.Exception):
            _resolve_local_python_image()(client)
