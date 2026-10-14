r"""检查 19 的门：e2e 轨上"测试步骤写了、:3000 上的实体没有"。

第一百一十一批的取证链（run 38332373255，commit `779fd23b`，push 后第一次）：
第一百零八批把 `Run Flyway migrations` 修绿之后，`Run full E2E suite` **从出生起第一次真的
被执行**，于是暴露出它下面那一层——

  - e2e.yml 两个 job 的步骤序列都是 `npm ci` → `playwright install` → `npx playwright test`，
    中间没有任何一步起前端；
  - 同时 `playwright.config.ts:31-38` 在 `CI` 为真时把 `webServer` 置成 `undefined`
    （本地开发靠它起 `npm run dev`），于是 CI 里没有任何进程监听 :3000；
  - 结果 35 失败 / 28 通过 / 10 跳过，35 条报错同一条：
    `Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/…`。
    同 job 的 `Wait for Java backend` / `Wait for Python AI` 两条轮询都是绿的，缺的正是前端那条。

前三次 e2e run（38233532705 / 38134153616 / 38025985552）的 `failed_steps` 都是
`["Run Flyway migrations"]` 且测试步骤 `skipped`，所以这不是回归，是被上一层挡着的既有缺陷。

行为侧的本地实测（不由文本门冒充）：`npm run dev` 起 vite 后 `curl -sf http://localhost:3000/`
返回 **200**（冷启动 ready in 10354 ms，日志含"Re-optimizing dependencies"），`/api/health`
经代理返回 502（本机没有 8080，CI 上有），杀掉进程后同一请求返回 000/refused ——
正是那 35 条红的签名。

本文件钉住：真仓库绿、并进默认全跑档、七种坏形状各红一次、适用面下界，
以及一条 PyYAML 独立 oracle（文本解析器不与 YAML 分歧，端口两处同源）。
"""

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"
E2E_YML = ROOT / ".github" / "workflows" / "e2e.yml"
PW_CONFIG = ROOT / "hfusionhub-frontend" / "playwright.config.ts"


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_e2e_frontend_gate", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── fixture：一个"应当绿"的最小 e2e.yml 与一份同源的 playwright.config.ts ──────

CONFIG_GREEN = """export default defineConfig({
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
  },
  webServer: CI
    ? undefined
    : {
        command: 'npm run dev',
        port: 3000,
      },
})
"""


def _steps(
    *,
    serve: bool = True,
    serve_body: str = "npm run dev &",
    probe: bool = True,
    probe_port: str = "3000",
    probe_exit: bool = True,
    serve_before_ci: bool = False,
    test_body: str | None = "npx playwright test --project=chromium",
) -> str:
    install = "      - name: Install frontend dependencies\n        run: npm ci\n"
    serve_step = f"      - name: Start frontend dev server\n        run: {serve_body}\n"
    probe_step = (
        "      - name: Wait for frontend dev server\n"
        "        run: |\n"
        "          for i in $(seq 1 30); do\n"
        f"            curl -sf http://localhost:{probe_port}/ && exit 0\n"
        "            sleep 2\n"
        "          done\n"
        '          echo "Frontend dev server failed to start within 60s"\n'
        + ("          exit 1\n" if probe_exit else '          echo "keep going"\n')
    )
    test_step = (
        "      - name: Run full E2E suite\n"
        '        env:\n          CI: "true"\n'
        f"        run: {test_body}\n"
        if test_body
        else ""
    )
    if serve_before_ci:
        return serve_step + (probe_step if probe else "") + install + test_step
    return install + (serve_step if serve else "") + (probe_step if probe else "") + test_step


def _workflow(steps_kwargs=None, *, jobs=("e2e-smoke", "e2e-full")) -> str:
    steps_kwargs = steps_kwargs or {}
    text = "name: E2E Tests\non:\n  push:\n    branches: [main]\njobs:\n"
    for name in jobs:
        text += f"  {name}:\n    runs-on: ubuntu-latest\n    steps:\n" + _steps(**steps_kwargs)
    return text


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """把检查 19 的两个入参文件搬到临时仓库面上，返回 (module, 写文件用的 helper)。"""
    module = _load_checker()
    workflow = tmp_path / "e2e.yml"
    config = tmp_path / "playwright.config.ts"
    workflow.write_text(_workflow(), encoding="utf-8")
    config.write_text(CONFIG_GREEN, encoding="utf-8")
    monkeypatch.setattr(module, "E2E_WORKFLOW", workflow)
    monkeypatch.setattr(module, "PLAYWRIGHT_CONFIG", config)
    monkeypatch.setattr(module, "problems", [])
    return module, workflow, config


def _offenders(module):
    return module._e2e_frontend_offenders()[0]


# ── 一、真仓库：绿 + 适用面正是量到的那两个 job ─────────────────────────────


class TestRealRepo:
    def test_repo_is_green(self):
        module = _load_checker()
        offenders, jobs = module._e2e_frontend_offenders()
        assert offenders == [], "\n".join(offenders)
        assert jobs == 2, f"应当扫到 2 个含 playwright 测试的 job，实际 {jobs}"

    def test_repo_prints_ok_line(self, capsys):
        module = _load_checker()
        module.problems.clear()
        module.check_e2e_frontend_server()
        out = capsys.readouterr().out
        assert "e2e 轨前端服务契约" in out and "2 个" in out
        assert module.problems == []

    def test_wired_into_default_full_run(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()") :]
        assert "--e2e-frontend-server" in main_body
        all_mode = main_body[
            main_body.index("args = parser.parse_args()") : main_body.index("if args.tenant_columns:")
        ]
        assert all_mode.count("args.e2e_frontend_server") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_e2e_frontend_server()" in main_body

    def test_repo_applicability_floor_is_named(self):
        module = _load_checker()
        assert module.E2E_TEST_JOBS == {"e2e-smoke", "e2e-full"}


# ── 二、独立 oracle：YAML 解析器读到的形状与文本解析器一致 ─────────────────


class TestYamlOracle:
    def test_text_parser_agrees_with_yaml_on_step_order(self):
        """有名字的步骤：顺序与内容与 PyYAML 逐条相同；无名步骤的条数也钉住。

        已知噪声一条：`services.*.ports` 里的 `- 3306:3306` 会被步骤起始式
        （`- <key>:`）认成一个无名步骤，所以无名侧按「YAML 的 uses 步骤数 ＋ 每 job 两条端口」
        断言——把这条也算进去，解析器哪天多吞或少吞都会红，而不是靠"过滤掉"糊过去。
        """
        module = _load_checker()
        doc = yaml.safe_load(E2E_YML.read_text(encoding="utf-8"))
        steps = module._workflow_steps(E2E_YML)
        port_lines_per_job = 2  # mysql 的 - 3306:3306 与 redis 的 - 6379:6379
        for name, body in doc["jobs"].items():
            job_range = [(start, end) for job, start, end in module._workflow_job_ranges(E2E_YML) if job == name]
            in_job = [s for s in steps if any(start <= s["lineno"] <= end for start, end in job_range)]
            yaml_steps = [s for s in body["steps"] if isinstance(s, dict)]
            assert [s["name"] for s in in_job if s["name"]] == [
                s["name"] for s in yaml_steps if s.get("name")
            ], f"{name}: 文本解析器与 YAML 在有名步骤上分歧"
            unnamed_yaml = sum(1 for s in yaml_steps if not s.get("name"))
            unnamed_text = sum(1 for s in in_job if not s["name"])
            assert unnamed_text == unnamed_yaml + port_lines_per_job, (
                f"{name}: 无名步骤条数漂移（YAML {unnamed_yaml} ＋端口 {port_lines_per_job}"
                f"≠ 文本 {unnamed_text}），端口行的行数或步骤起始式变了"
            )

    def test_every_playwright_job_has_a_server_before_it_in_yaml(self):
        """不看文本解析器，只用 YAML：测试步骤前必须有起前端步骤，且在 npm ci 之后。"""
        doc = yaml.safe_load(E2E_YML.read_text(encoding="utf-8"))
        count = 0
        for name, body in doc["jobs"].items():
            runs = [(i, (s.get("run") or "")) for i, s in enumerate(body["steps"])]
            tests = [i for i, r in runs if "npx playwright test" in r]
            if not tests:
                continue
            count += 1
            test_at = tests[0]
            serve = [i for i, r in runs[:test_at] if re.search(r"npm run (dev|preview)\b.*&\s*$", r)]
            install = [i for i, r in runs[:test_at] if "npm ci" in r]
            assert serve, f"{name}: YAML 里也没有起前端的步骤"
            assert install, f"{name}: 没有 npm ci 步骤"
            assert max(serve) > max(install), f"{name}: 起前端排在装依赖之前"
            probe = [
                i
                for i, r in runs
                if max(serve) < i < test_at and re.search(r"https?://[a-z0-9.-]+:(\d+)", r)
            ]
            assert probe, f"{name}: 起了前端却没有等待探针"
            assert "exit 1" in runs[probe[-1]][1], f"{name}: 探针超时不 fail"
        assert count == 2

    def test_probe_port_equals_base_url_port(self):
        """端口两处同源：探针 URL 的端口必须等于 playwright.config.ts 的 baseURL 端口。"""
        config = PW_CONFIG.read_text(encoding="utf-8")
        port = re.search(r"baseURL:[^\n]*?://[A-Za-z0-9_.-]+:(\d+)", config).group(1)
        doc = yaml.safe_load(E2E_YML.read_text(encoding="utf-8"))
        seen = set()
        for body in doc["jobs"].values():
            for step in body["steps"]:
                for found in re.findall(r"https?://[a-z0-9.-]+:(\d+)", step.get("run") or ""):
                    seen.add(found)
        assert port in seen and "3000" == port

    def test_config_does_not_autostart_under_ci(self):
        """CI 档归工作流管：config 里 `webServer: CI ? undefined : {…}` 那个 undefined 是前提。"""
        module = _load_checker()
        text = PW_CONFIG.read_text(encoding="utf-8")
        assert module._playwright_ci_autostarts(text) is False

    def test_multiline_ternary_is_read_as_one_logical_line(self):
        """续行教训的同一条规则（第一百零九批检查 18）：跨三行的三元式必须读得出。"""
        module = _load_checker()
        assert "webServer: CI\n    ? undefined\n    : {" in CONFIG_GREEN
        assert module._playwright_ci_autostarts(CONFIG_GREEN) is False
        assert module._playwright_ci_autostarts("webServer: { command: 'npm run dev' }") is True
        assert module._playwright_ci_autostarts("webServer: CI ? { port: 3000 } : undefined") is True


# ── 三、坏形状各红一次 ──────────────────────────────────────────────────────


class TestBadShapes:
    def test_missing_server_step_is_red(self, gate):
        module, _, _ = gate
        module.E2E_WORKFLOW.write_text(_workflow({"serve": False}), encoding="utf-8")
        offenders = _offenders(module)
        assert len(offenders) == 2
        assert all("ERR_CONNECTION_REFUSED" in o for o in offenders), offenders

    def test_port_drift_between_probe_and_config_is_red(self, gate):
        module, _, _ = gate
        module.E2E_WORKFLOW.write_text(_workflow({"probe_port": "4173"}), encoding="utf-8")
        offenders = _offenders(module)
        assert len(offenders) == 2
        assert all("两处不同源" in o for o in offenders), offenders

    def test_probe_without_failure_exit_is_red(self, gate):
        module, _, _ = gate
        module.E2E_WORKFLOW.write_text(_workflow({"probe_exit": False}), encoding="utf-8")
        offenders = _offenders(module)
        assert all("没有 exit 1" in o for o in offenders), offenders

    def test_server_started_before_install_is_red(self, gate):
        module, _, _ = gate
        module.E2E_WORKFLOW.write_text(_workflow({"serve_before_ci": True}), encoding="utf-8")
        offenders = _offenders(module)
        assert all("node_modules 还不存在" in o for o in offenders), offenders

    def test_missing_probe_is_red(self, gate):
        module, _, _ = gate
        module.E2E_WORKFLOW.write_text(_workflow({"probe": False}), encoding="utf-8")
        offenders = _offenders(module)
        assert all("等待探针" in o for o in offenders), offenders

    def test_double_owner_is_red(self, gate):
        """config 在 CI 档也自起 webServer ＋ 工作流显式起 = 同一端口两个主人。"""
        module, _, config = gate
        config.write_text(CONFIG_GREEN.replace("? undefined", "? { port: 3000 }"), encoding="utf-8")
        module.problems.clear()
        module.check_e2e_frontend_server()
        joined = "\n".join(module.problems)
        assert "EADDRINUSE" in joined, joined

    def test_empty_applicability_is_red(self, gate):
        """两个 job 的测试步骤都没了 ⇒ 适用面为空判红（删掉红步骤不能让门变绿）。"""
        module, workflow, _ = gate
        workflow.write_text(_workflow({"test_body": None}), encoding="utf-8")
        offenders = _offenders(module)
        assert any("适用面为空" in o for o in offenders), offenders

    def test_shrunken_applicability_is_red(self, gate):
        """只剩一个 job 在跑 playwright ⇒ 另一条链没人核了，判红而不是少报。"""
        module, workflow, _ = gate
        text = _workflow()
        smoke_start = text.index("  e2e-smoke:")
        smoke_end = text.index("  e2e-full:")
        workflow.write_text(text[:smoke_start] + text[smoke_end:], encoding="utf-8")
        offenders = _offenders(module)
        assert any("适用面缩小了" in o and "e2e-smoke" in o for o in offenders), offenders

    def test_renamed_test_command_narrows_applicability(self, gate):
        """命令改名（如换 playwright test 直调）不该把门变绿。"""
        module, workflow, _ = gate
        workflow.write_text(
            _workflow({"test_body": "node_modules/.bin/playwright test"}), encoding="utf-8"
        )
        offenders = _offenders(module)
        assert any("适用面为空" in o for o in offenders), offenders

    def test_unparseable_base_url_port_is_red(self, gate):
        module, _, config = gate
        config.write_text("export default defineConfig({ use: { baseURL: process.env.BASE_URL } })")
        offenders = _offenders(module)
        assert any("读不到端口" in o for o in offenders), offenders

    def test_missing_workflow_file_is_red_not_quiet(self, gate):
        module, workflow, _ = gate
        workflow.unlink()
        offenders = _offenders(module)
        assert offenders and any("workflow 文件不存在" in o for o in offenders)

    def test_missing_config_file_is_red_not_quiet(self, gate):
        module, _, config = gate
        config.unlink()
        offenders = _offenders(module)
        assert offenders and any("无从同源" in o for o in offenders)

    def test_green_fixture_has_no_offenders(self, gate):
        module, _, _ = gate
        offenders, jobs = module._e2e_frontend_offenders()
        assert offenders == [], "\n".join(offenders)
        assert jobs == 2
