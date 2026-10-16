r"""检查 20 的门：e2e 轨用的后端把**被测端点的开关**显式打开了没有。

第一百一十三批的取证链（run 38343229817 的 `e2e-results-full` ＋ `playwright-traces` 工件，
commit `418596c4`）：`demo-data.spec.ts` 三条红在第一百一十一批登记时写的是"测试侧陈旧期望"，
trace 打开后它们的报错都是 `page.waitForResponse: Timeout 10000ms exceeded`
（`demo-data.spec.ts:23`/`:40`/`:72`），但请求**确实发出并回来了**——

  - `POST http://localhost:3000/api/demo/import` → **HTTP 200**，信封却是
    `{"code":403,"message":"演示数据功能已关闭（DEMO_ENDPOINTS_ENABLED=false）…","data":null}`
    （三条的 traceId `d36804ec03644249b011b204d5d97713` / `ac1ca5cb04b74d84b64e47721f767fce` /
    `57e397cc38ac42c6adee633a75fafd49`）；
  - 门在 `java-backend/src/main/java/com/hfusionhub/controller/DemoController.java:39/44`，
    值来自 `application.yml:177` 的 `${DEMO_ENDPOINTS_ENABLED:false}`；
  - `.github/workflows/e2e.yml` 两个 job 的 `Start Java backend` env（改前 `:84-105`、`:236-257`）
    **从没带过这个键**，而 `docker/docker-compose.yml:272` 与 `docker/.env:24` 都写着 `true`
    ——dev 栈开、CI 档关，用例按"开着"写期望。

HTTP 状态是 200，所以这一步不会变红、探针也不会变红、API 也正常——死的是用例读到的是
门控关闭的响应。这条正是第一百零九批"配置写了、容器里没有实体"同族的另一面：
**开关有默认值、CI 档没声明，于是跑的是一个语义不同的后端**。

同一条 trace 的时间轴还量到第二层：请求起于 `_monotonicTime 114340`、历时 121 ms
（≈`114461` 落地），而 `waitForResponse` 到 `114773.2` 才注册——spec 写的是
`await click()` **之后**才注册 waiter。开关关着时后端 16 ms 短路返回，把这个竞态显形了。
本检查只闭合最外那一层（CI 起的后端是不是用例假定的那个后端），**不判竞态、也不判
陈旧 label**（`li:has-text("知识库文档")` vs `BidDemoImportServiceImpl.java:149-152` 实际发的
「招标文件知识库／企业资质库／历史标书库／示例投标项目」）——那两层写在
`docs/CI_GATES.md` 的检查 20 一节与 `docs/CLEANUP_BACKLOG.md` 里，未处置。

本文件钉住：真仓库绿、并进默认全跑档、缺键/值不对/注释冒充/键放错步骤各红一次、
适用面下界与"跑 playwright 却没起后端"，另加一条 PyYAML 独立 oracle（不看文本解析器），
和一条"workflow 钉值 == dev compose 钉值"的跨文件同源判定。
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"
E2E_YML = ROOT / ".github" / "workflows" / "e2e.yml"


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_e2e_backend_flag_gate", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


JAVA_ENV_GREEN = """          SERVER_PORT: "8080"
          SPRING_DATA_REDIS_PORT: 6379
          ADMIN_PASSWORD: "admin123"
          DEMO_ENDPOINTS_ENABLED: "true"
"""


def _job(name: str, *, java_env: str = JAVA_ENV_GREEN, backend: bool = True,
         test: str = "npx playwright test --project=chromium", job_env: str = "") -> str:
    text = f"  {name}:\n    runs-on: ubuntu-latest\n"
    if job_env:
        text += "    env:\n" + job_env
    text += "    steps:\n"
    text += "      - name: Checkout\n        uses: actions/checkout@v4\n"
    if backend:
        text += '      - name: Start Java backend\n        env:\n' + java_env + "        run: mvn --batch-mode spring-boot:run &\n"
    text += f'      - name: Run full E2E suite\n        env:\n          CI: "true"\n        run: {test}\n'
    return text


def _workflow(**job_kwargs) -> str:
    return ("name: E2E Tests\non:\n  push:\n    branches: [main]\njobs:\n"
            + _job("e2e-smoke", **job_kwargs)
            + _job("e2e-full", **job_kwargs))


@pytest.fixture
def gate(tmp_path, monkeypatch):
    module = _load_checker()
    workflow = tmp_path / "e2e.yml"
    workflow.write_text(_workflow(), encoding="utf-8")
    monkeypatch.setattr(module, "E2E_WORKFLOW", workflow)
    monkeypatch.setattr(module, "problems", [])
    return module, workflow


def _offenders(module):
    return module._e2e_backend_flag_offenders()[0]


# ── 一、真仓库：绿 + 接线 + 适用面 ──────────────────────────────────────────


class TestRealRepo:
    def test_repo_is_green(self):
        module = _load_checker()
        offenders, jobs = module._e2e_backend_flag_offenders()
        assert offenders == [], "\n".join(offenders)
        assert jobs == 2, f"应当核到 2 个 job，实际 {jobs}"

    def test_repo_prints_ok_line(self, capsys):
        module = _load_checker()
        module.problems.clear()
        module.check_e2e_backend_feature_flags()
        out = capsys.readouterr().out
        assert "e2e 轨后端特性开关" in out and "2 个" in out
        assert module.problems == []

    def test_wired_into_default_full_run(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--e2e-backend-feature-flags" in main_body
        all_mode = main_body[
            main_body.index("args = parser.parse_args()"): main_body.index("if args.tenant_columns:")
        ]
        assert all_mode.count("args.e2e_backend_feature_flags") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_e2e_backend_feature_flags()" in main_body

    def test_expected_value_is_the_one_the_specs_assume(self):
        """钉住期望值本身：用例假定 true，`false` 不是"也算声明过"。"""
        module = _load_checker()
        assert module.E2E_BACKEND_FLAG_EXPECTED == {"DEMO_ENDPOINTS_ENABLED": "true"}


# ── 二、独立 oracle：YAML 读到的形状与文本解析器一致 ─────────────────────────


class TestYamlOracle:
    def test_every_playwright_job_declares_the_flag_in_yaml(self):
        """不看文本解析器：每个跑 playwright 的 job，job 级或起后端步骤的 env 里必须有键。"""
        doc = yaml.safe_load(E2E_YML.read_text(encoding="utf-8"))
        count = 0
        for name, body in doc["jobs"].items():
            steps = body["steps"]
            if not any("npx playwright test" in (s.get("run") or "") for s in steps):
                continue
            count += 1
            backend = [s for s in steps if "spring-boot:run" in (s.get("run") or "")]
            assert backend, f"{name}: YAML 里没有起 java 后端的步骤"
            rows = []
            for env in [body.get("env") or {}] + [s.get("env") or {} for s in backend]:
                rows.extend(env.keys())
            assert "DEMO_ENDPOINTS_ENABLED" in rows, f"{name}: YAML 里没声明 DEMO_ENDPOINTS_ENABLED"
            values = [s["env"]["DEMO_ENDPOINTS_ENABLED"] for s in backend
                      if "DEMO_ENDPOINTS_ENABLED" in (s.get("env") or {})]
            assert values and str(values[0]) == "true", f"{name}: YAML 读到的值是 {values}"
        assert count == 2

    def test_flag_is_not_pinned_only_in_the_workflow(self):
        """同源核对：dev compose 与 CI 档写的是同一个值，不是各钉一半。"""
        compose = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
        workflow = E2E_YML.read_text(encoding="utf-8")
        assert 'DEMO_ENDPOINTS_ENABLED: "true"' in compose
        assert 'DEMO_ENDPOINTS_ENABLED: "true"' in workflow


# ── 三、坏形状各红一次 ──────────────────────────────────────────────────────


class TestBadShapes:
    def test_missing_key_is_red_for_every_job(self, gate):
        module, workflow = gate
        workflow.write_text(_workflow(java_env=JAVA_ENV_GREEN.replace(
            '          DEMO_ENDPOINTS_ENABLED: "true"\n', "")), encoding="utf-8")
        offenders = _offenders(module)
        assert len(offenders) == 2, offenders
        assert all("没有声明 `DEMO_ENDPOINTS_ENABLED`" in o and "信封 403" in o for o in offenders)

    def test_declared_but_false_is_red(self, gate):
        """键存在≠开关打开：写 false 时被测面照样门控关闭。"""
        module, workflow = gate
        workflow.write_text(_workflow(java_env=JAVA_ENV_GREEN.replace(
            'DEMO_ENDPOINTS_ENABLED: "true"', 'DEMO_ENDPOINTS_ENABLED: "false"')), encoding="utf-8")
        offenders = _offenders(module)
        assert all("用例假定 `true`" in o for o in offenders), offenders

    def test_unquoted_true_is_accepted(self, gate):
        """YAML 里 `true` 与 `"true"` 解析后都是真值，文本门不能因为引号判红。"""
        module, workflow = gate
        workflow.write_text(_workflow(java_env=JAVA_ENV_GREEN.replace(
            'DEMO_ENDPOINTS_ENABLED: "true"', "DEMO_ENDPOINTS_ENABLED: true")), encoding="utf-8")
        assert _offenders(module) == []

    def test_commented_key_does_not_count_as_declared(self, gate):
        """注释行不是声明：`# DEMO_ENDPOINTS_ENABLED: "true"` 不能让门变绿。"""
        module, workflow = gate
        workflow.write_text(_workflow(java_env=JAVA_ENV_GREEN.replace(
            '          DEMO_ENDPOINTS_ENABLED: "true"',
            '          # DEMO_ENDPOINTS_ENABLED: "true"')), encoding="utf-8")
        offenders = _offenders(module)
        assert len(offenders) == 2, offenders

    def test_key_on_the_wrong_step_is_red(self, gate):
        """键必须落在"起后端的那一步"或 job 级 env——挂到前端步骤上对 java 进程没有意义。"""
        module, workflow = gate
        text = _workflow(java_env=JAVA_ENV_GREEN.replace(
            '          DEMO_ENDPOINTS_ENABLED: "true"\n', "")).replace(
            '      - name: Run full E2E suite\n        env:\n          CI: "true"\n',
            '      - name: Run full E2E suite\n        env:\n          CI: "true"\n'
            '          DEMO_ENDPOINTS_ENABLED: "true"\n')
        workflow.write_text(text, encoding="utf-8")
        offenders = _offenders(module)
        assert len(offenders) == 2, offenders

    def test_job_level_env_counts_as_declared(self, gate):
        """job 级 env（4 空格那一列）对步骤同样生效，应当算声明。"""
        module, workflow = gate
        text = _workflow(java_env=JAVA_ENV_GREEN.replace(
            '          DEMO_ENDPOINTS_ENABLED: "true"\n', ""),
            job_env='      DEMO_ENDPOINTS_ENABLED: "true"\n')
        workflow.write_text(text, encoding="utf-8")
        assert _offenders(module) == []

    def test_playwright_without_backend_is_red(self, gate):
        """跑测试却没起后端 ⇒ 被测面由谁提供换了地方，判红而不是少报。"""
        module, workflow = gate
        workflow.write_text(_workflow(backend=False), encoding="utf-8")
        offenders = _offenders(module)
        assert any("没有起 java 后端的步骤" in o for o in offenders), offenders
        assert any("适用面为空" in o for o in offenders), offenders

    def test_empty_applicability_is_red(self, gate):
        """测试步骤全删 ⇒ 适用面为空判红（删掉红步骤不能让门变绿）。"""
        module, workflow = gate
        workflow.write_text(_workflow(test=""), encoding="utf-8")
        offenders = _offenders(module)
        assert any("适用面为空" in o for o in offenders), offenders

    def test_renamed_test_command_narrows_applicability(self, gate):
        module, workflow = gate
        workflow.write_text(_workflow(test="node_modules/.bin/playwright test"), encoding="utf-8")
        offenders = _offenders(module)
        assert any("适用面为空" in o for o in offenders), offenders

    def test_shrunken_job_set_is_red(self, gate):
        """只剩一个 job 跑 playwright ⇒ 另一条链没人核了。"""
        module, workflow = gate
        text = _workflow()
        workflow.write_text(text[:text.index("  e2e-full:")] + "  unrelated:\n    runs-on: x\n    steps: []\n",
                            encoding="utf-8")
        offenders = _offenders(module)
        assert any("适用面缩小了" in o and "e2e-full" in o for o in offenders), offenders

    def test_missing_workflow_is_red_not_quiet(self, gate):
        module, workflow = gate
        workflow.unlink()
        offenders = _offenders(module)
        assert offenders and any("workflow 文件不存在" in o for o in offenders)

    def test_green_fixture_has_no_offenders(self, gate):
        module, _ = gate
        offenders, jobs = module._e2e_backend_flag_offenders()
        assert offenders == [], "\n".join(offenders)
        assert jobs == 2
