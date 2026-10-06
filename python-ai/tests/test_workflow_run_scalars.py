r"""workflow 的 `run:` 标量形态：带续行的命令必须是块标量，否则门禁从未执行。

第九十七批在真 CI 上量到的：招投标三个竖门自 2026-08-25（`aabd3df6` / `f684d6bb`）起
每次都退出码 2，`unrecognized arguments`。起因是 YAML——`run: python … \` 后面跟缩进的
`--cases …`，整段是**一个 plain 多行标量**，换行被折叠成空格，shell 于是收到 `\ `
（转义的空格）而不是续行，argv 变成 `' --cases'`。改成块标量 `run: |` 之后，`\`+换行
才是 shell 的行继续符。

这类缺陷的可怕之处在于它**不会让任何一步变红**：门禁消失比门禁失败更安静。所以本文件把
`scripts/static-checks.py` 的检查 14 钉住三件事——真仓库绿、真的接进了默认全跑档、以及
注入历史形态时会红；并用 PyYAML（生产码只用标准库，这里故意换一个 oracle）证明
"折叠成一行"的推断不是纸上推理，而是 argparse 真会拒的形状。
"""

import importlib.util
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
EVAL_OFFLINE = ROOT / "python-ai" / "scripts" / "eval_offline.py"

SUITES = ("suite", "suite_bid", "suite_bid_construction", "suite_bid_it")
JOB = "eval-offline"
HEADER = f"""name: ci
on: push
jobs:
  {JOB}:
    defaults:
      run:
        working-directory: python-ai
    steps:
      - uses: actions/checkout@v4
"""


def _gate(suite: str, form: str) -> str:
    """同一个门的几种写法：块标量（正确）、行内反斜杠续行（历史缺陷）、
    plain 折行（无反斜杠）、单行（合法）、整步消失（门禁消失形态）。
    """
    lines = [
        f"      - name: Run {suite} offline evaluation gate",
        "        run: python scripts/eval_offline.py \\",
        f"          --cases evaluation/{suite}/cases.jsonl \\",
        "          --fail-on-regression",
    ]
    if form == "block":
        return (
            f"      - name: Run {suite} offline evaluation gate\n"
            "        run: |\n"
            "          python scripts/eval_offline.py \\\n"
            f"            --cases evaluation/{suite}/cases.jsonl \\\n"
            "            --fail-on-regression\n"
        )
    if form == "plain_fold":
        return (
            f"      - name: Run {suite} offline evaluation gate\n"
            "        run: python scripts/eval_offline.py\n"
            f"          --cases evaluation/{suite}/cases.jsonl\n"
            "          --fail-on-regression\n"
        )
    if form == "single_line":
        return (
            f"      - name: Run {suite} offline evaluation gate\n"
            f"        run: python scripts/eval_offline.py --cases evaluation/{suite}/cases.jsonl"
            " --fail-on-regression\n"
        )
    if form == "dropped":
        return ""
    if form != "inline_backslash":
        raise ValueError(form)
    return "\n".join(lines) + "\n"


def _ci_text(forms: dict[str, str]) -> str:
    return HEADER + "".join(_gate(suite, forms.get(suite, "block")) for suite in SUITES)


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_static_checks", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_fixture(tmp_path: Path, *, forms: dict[str, str] | None = None, drop: set[str] = frozenset()) -> object:
    """写一份四门齐全、全部块标量的最小仓库，再按需把某个门换成坏写法或删掉。

    drop 里的名字对应检查 14 的四个可钉住的实体：ci.yml、某个套件的 cases.jsonl、
    评测入口脚本。
    """
    forms = forms or {}
    module = _load_checker()
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    suites_root = tmp_path / "evaluation"
    entry = tmp_path / "eval_offline.py"

    # 另一个 workflow 一直在：删掉 ci.yml 后目录非空，门禁才会走到"ci.yml 缺失"这一支
    # 而不是先撞上"目录下没有 workflow 文件"就 return。
    (workflow_dir / "release.yml").write_text(
        HEADER.replace(f"  {JOB}:", "  release:")
        + "      - run: echo release\n"
        + "      - name: multi\n        run: |\n          echo a \\\n            echo b\n",
        encoding="utf-8",
    )
    module.WORKFLOW_DIR = workflow_dir
    module.CI_WORKFLOW = workflow_dir / "ci.yml"
    module.EVAL_SUITES_ROOT = suites_root
    module.EVAL_OFFLINE_ENTRY = entry

    if "ci" not in drop:
        module.CI_WORKFLOW.write_text(_ci_text(forms), encoding="utf-8")
    if "cases" not in drop:
        for suite in SUITES:
            case_dir = suites_root / suite
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "cases.jsonl").write_text("{}\n", encoding="utf-8")
    if "entry" not in drop:
        entry.write_text("def main():\n    pass\n", encoding="utf-8")

    module.problems.clear()
    return module


def _steps(doc: dict) -> list[dict]:
    return [step for job in doc["jobs"].values() for step in job.get("steps", [])]


def _eval_gate_runs(doc: dict) -> list[tuple[str, str]]:
    """(步骤名, shell 实际收到的脚本) —— 只取调用 eval_offline.py 的门。"""
    return [(step["name"], step["run"]) for step in _steps(doc) if "scripts/eval_offline.py" in step.get("run", "")]


def _bash_argv(script: str) -> list[str]:
    r"""shell 视角的 argv：先吃掉 `\`+换行（行继续符），再按 POSIX 规则切词。"""
    return shlex.split(script.replace("\\\n", ""), posix=True)


class TestGateOnTheRepo:
    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--workflow-run-scalars"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_gate_is_in_the_default_all_mode(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()") :]
        assert "--workflow-run-scalars" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()") : main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.workflow_run_scalars") >= 2, f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        assert "check_workflow_run_scalars()" in main_body

    def test_the_four_gates_are_block_scalars_in_the_repo(self):
        """正向声称：门禁只查形状，这四道门必须真的还是块标量且各带自己的 --cases。"""
        doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
        runs = _eval_gate_runs(doc)
        assert len(runs) == len(SUITES), f"评测门数量应为 {len(SUITES)}，实际 {len(runs)}"
        for name, script in runs:
            assert script.startswith("python"), f"{name} 不是块标量（行内值被 YAML 折过）"
            argv = _bash_argv(script)
            assert argv[0] == "python" and argv[1] == "scripts/eval_offline.py", name
            assert "--cases" in argv, f"{name} 折叠后没有独立的 --cases 选项：{argv}"
            cases = argv[argv.index("--cases") + 1]
            assert cases in {f"evaluation/{suite}/cases.jsonl" for suite in SUITES}, name

    def test_gate_paths_resolve_under_the_declared_working_directory(self):
        """`--cases evaluation/…` 与 `scripts/eval_offline.py` 都是相对路径：
        它们能不能命中，全看 job 声明的 working-directory。这一条把那个前提也钉住。
        """
        doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
        cwd = doc["jobs"][JOB]["defaults"]["run"]["working-directory"]
        base = ROOT / cwd
        assert (base / "scripts" / "eval_offline.py").is_file(), "入口相对 working-directory 不存在"
        for _, script in _eval_gate_runs(doc):
            argv = _bash_argv(script)
            if "--cases" in argv:
                assert (base / argv[argv.index("--cases") + 1]).is_file(), script[:80]


class TestContractWithArgparse:
    """形状对了不等于门会跑：选项名拼错同样退出码 2，而 CI 里那一步照样没人看。"""

    def test_every_flag_the_gates_pass_is_declared_by_argparse(self):
        declared = set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', EVAL_OFFLINE.read_text(encoding="utf-8")))
        assert declared, "没从 eval_offline.py 解析出任何选项，这个契约测试会是空转"
        doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
        for name, script in _eval_gate_runs(doc):
            for token in _bash_argv(script):
                if token.startswith("--") and token != "--":
                    assert token in declared, f"{name} 传了 argparse 不认识的 {token}"

    def test_the_historical_fold_is_what_argparse_rejects(self):
        """红判据不是假想：把历史写法交给 YAML 解析，argv 里就是带前导空格的 ' --cases'。"""
        doc = yaml.safe_load(HEADER + _gate("suite_bid", "inline_backslash"))
        name, script = _eval_gate_runs(doc)[0]
        argv = _bash_argv(script)
        offenders = [token for token in argv if token.startswith(" ")]
        assert offenders, f"折叠形态应产生带前导空格的 token，实际 argv={argv!r}"
        assert offenders[0].strip() == "--cases", offenders
        assert "--cases" not in argv, "选项名被空格污染后 argparse 就不认它了"


class TestGateFlagsDrift:
    def test_inline_run_ending_with_backslash_is_red(self, tmp_path):
        module = _repo_fixture(tmp_path, forms={"suite_bid": "inline_backslash"})
        module.check_workflow_run_scalars()
        assert module.problems, "回到第九十七批修掉前的写法时门禁必须报红"
        assert "被转义的空格" in module.problems[0]

    def test_plain_multiline_fold_is_red_even_without_backslashes(self, tmp_path):
        """没写反斜杠也照样是 plain 多行标量：命令会被拼成一行，红判据不能只盯反斜杠。"""
        module = _repo_fixture(tmp_path, forms={"suite_bid_it": "plain_fold"})
        module.check_workflow_run_scalars()
        assert module.problems, "plain 多行标量的折叠必须报红"
        assert "plain 多行标量" in module.problems[0]

    def test_the_broken_gate_does_not_hurt_the_other_gates(self, tmp_path):
        """报告要指到出事的那个门，不能整段一锅端——否则修完一个仍不知道另一个在不在。"""
        module = _repo_fixture(tmp_path, forms={"suite_bid_construction": "inline_backslash"})
        module.check_workflow_run_scalars()
        flagged = [line for line in module.problems[0].splitlines() if "run 用行内标量" in line]
        assert len(flagged) == 1, module.problems

    def test_block_scalar_with_continuations_is_accepted(self, tmp_path):
        module = _repo_fixture(tmp_path)
        module.check_workflow_run_scalars()
        assert not module.problems, f"全部块标量的仓库不该被判红：{module.problems}"

    def test_single_line_run_is_accepted(self, tmp_path):
        module = _repo_fixture(tmp_path, forms={"suite": "single_line"})
        module.check_workflow_run_scalars()
        assert not module.problems, f"单行命令是合法形态：{module.problems}"

    def test_a_gate_that_silently_disappears_is_red(self, tmp_path):
        """门禁消失比门禁变红更安静——这正是本次缺陷的形态，必须单独能红。"""
        module = _repo_fixture(tmp_path, forms={"suite_bid": "dropped"})
        module.check_workflow_run_scalars()
        assert module.problems, "招投标门整步消失时门禁必须报红"
        assert "suite_bid" in module.problems[0] and "门禁消失" in module.problems[0]

    def test_missing_cases_file_is_red(self, tmp_path):
        module = _repo_fixture(tmp_path)
        (tmp_path / "evaluation" / "suite_bid" / "cases.jsonl").unlink()
        module.check_workflow_run_scalars()
        assert module.problems, "ci.yml 引用的用例文件不存在时必须报红"
        assert "用例文件缺失" in module.problems[0]

    def test_missing_entry_script_is_red(self, tmp_path):
        module = _repo_fixture(tmp_path, drop={"entry"})
        module.check_workflow_run_scalars()
        assert module.problems, "评测入口脚本没了，四道门会一起变成找不到文件"
        assert "入口不存在" in module.problems[0]

    def test_missing_ci_is_red(self, tmp_path):
        module = _repo_fixture(tmp_path, drop={"ci"})
        module.check_workflow_run_scalars()
        assert module.problems, "ci.yml 缺失时不能因为扫不到 run 步骤就判绿"
        assert "ci.yml 缺失" in module.problems[0]
