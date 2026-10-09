r"""检查 15 的门禁测试：python 侧不许有裸本地墙钟读法，且每个 python 工作负载钉住 TZ=UTC。

第一百零二批在真容器里量到的形态：把进程时区翻到 Asia/Shanghai 后，TimeTool 给模型的
"现在几点"跟着变成 20:14，而同一瞬间的 UTC 是 12:14——因为 `datetime.now()` 的零参写法
读的是**进程时区**的墙钟，而三档 shipped 拓扑里没有任何一档为 python 工作负载声明过 `TZ`
（java 侧早在第九十六批就把 JVM/MySQL/JDBC 三张钟面钉死了，见检查 13）。

本文件把 `scripts/static-checks.py` 的检查 15 钉住三件事：对真仓库绿、真的接进了默认全跑档、
以及逐条注入漂移（代码裸读法 / TZ 缺失 / TZ 非 UTC / helm 死键 / 工作负载标记改名导致门禁消失）
时会红。工作负载集合那一条故意用 PyYAML 另写一个 oracle（生产码只用标准库，两边同时看错
同一个形状的概率才低）。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"

MARKERS = ("hfusionhub-python", "hfusionhub-plugin-runner", "Dockerfile.plugin-runner")

DEV_COMPOSE = """services:
  java-backend:
    image: ghcr.io/xiaodu55/hfusionhub-java:latest
    environment:
      SPRING_DATASOURCE_URL: jdbc:mysql://mysql8:3306/hfusionhub
  python-ai:
    image: ghcr.io/xiaodu55/hfusionhub-python:latest
    environment:
      TZ: "UTC"
      DEEPSEEK_API_KEY: placeholder-not-a-secret
  python-ai-worker:
    image: ghcr.io/xiaodu55/hfusionhub-python:latest
    environment:
      TZ: "UTC"
  plugin-runner:
    build:
      context: ..
      dockerfile: docker/Dockerfile.plugin-runner
    environment:
      TZ: "UTC"
"""

PROD_COMPOSE = """services:
  python-ai:
    image: ghcr.io/xiaodu55/hfusionhub-python:latest
    environment:
      TZ: "UTC"
  plugin-runner:
    image: ghcr.io/xiaodu55/hfusionhub-plugin-runner:latest
    environment:
      TZ: "UTC"
"""

HELM_VALUES = """pythonAi:
  enabled: true
  tz: "UTC"
  replicas: 2
pluginRunner:
  enabled: true
  tz: "UTC"
"""

HELM_PYTHON = """          env:
            - name: TZ
              value: {{ .Values.pythonAi.tz | quote }}
            - name: SERVER_PORT
              value: {{ .Values.pythonAi.port | quote }}
"""

HELM_PLUGIN_RUNNER = """          env:
            - name: TZ
              value: {{ .Values.pluginRunner.tz | quote }}
            - name: PLUGIN_ARTIFACTS_DIR
              value: /opt/plugin-artifacts
"""

CLEAN_APP_FILE = """from datetime import UTC, datetime


def generated_at() -> str:
    return datetime.now(UTC).isoformat()
"""

# 真仓库的 time_tool.py 正是这种形态：docstring 里解释"以前用的是 datetime.now()"。
# 不剥字符串的门禁会在自己的说明文字上判红。
DOCSTRING_ONLY_APP_FILE = '''"""时间工具。

此前用的是 `datetime.now()` 的裸本地墙钟——那一行现在是说明文字，不是代码。
"""

from datetime import UTC, datetime


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
'''


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_static_checks", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_fixture(tmp_path: Path, **overrides: str | None) -> object:
    """写一份"代码显式 UTC + 工作负载全钉 TZ"的最小仓库，再按需把某一面换成漂移值。

    None = 该面缺失：常量指向一个不存在的文件，而不是留着实仓库的路径默默通过。
    """
    texts = {
        "COMPOSE_DEV": DEV_COMPOSE,
        "COMPOSE_PROD": PROD_COMPOSE,
        "HELM_VALUES": HELM_VALUES,
        "HELM_PYTHON_TEMPLATE": HELM_PYTHON,
        "HELM_PLUGIN_RUNNER_TEMPLATE": HELM_PLUGIN_RUNNER,
    }
    texts.update(overrides)
    module = _load_checker()
    for name, default in texts.items():
        target = tmp_path / name
        if default is None:
            setattr(module, name, tmp_path / f"{name}.absent")
            continue
        target.write_text(default, encoding="utf-8")
        setattr(module, name, target)

    app_dir = tmp_path / "PYTHON_APP_DIR"
    app_dir.mkdir(exist_ok=True)
    (app_dir / "clean.py").write_text(CLEAN_APP_FILE, encoding="utf-8")
    module.PYTHON_APP_DIR = app_dir
    module.problems.clear()
    return module


def _add_app_file(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / "PYTHON_APP_DIR" / name).write_text(body, encoding="utf-8")


def _python_services(path: Path) -> list[tuple[str, str | None]]:
    """PyYAML 版的工作负载枚举：返回 [(服务名, 声明的 TZ 或 None), …]。"""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for name, service in (doc.get("services") or {}).items():
        shape = f"{service.get('image') or ''} {service.get('build') or ''}"
        if not any(marker in shape for marker in MARKERS):
            continue
        env = service.get("environment")
        if isinstance(env, dict):
            tz = env.get("TZ")
        elif isinstance(env, list):
            tz = next((e.get("value") for e in env if e.get("name") == "TZ"), None)
        else:
            tz = None
        out.append((name, tz))
    return sorted(out)


class TestGateOnTheRepo:
    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--python-clock-caliber"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_gate_is_in_the_default_all_mode(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--python-clock-caliber" in main_body
        all_mode = main_body[
            main_body.index("args = parser.parse_args()"):main_body.index("if args.tenant_columns:")
        ]
        assert all_mode.count("args.python_clock_caliber") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_python_clock_caliber()" in main_body

    def test_time_tool_is_the_explicit_utc_shape(self):
        """门禁绿之外，被修的那个工具必须真的显式声明口径，而不是只靠 TZ。"""
        source = (ROOT / "python-ai" / "app" / "core" / "tools" / "time_tool.py").read_text(
            encoding="utf-8"
        )
        assert "datetime.now(UTC)" in source, "TimeTool 又退回裸本地墙钟了"
        assert '"caliber": "UTC"' in source, "输出没带口径标签，读的人无法知道它是哪个墙钟"

    def test_every_shipped_python_workload_declares_tz_utc(self):
        """独立 oracle 点名当前应有的落点：门禁数到的集合一个都不能少。"""
        dev = _python_services(ROOT / "docker" / "docker-compose.yml")
        prod = _python_services(ROOT / "deploy" / "docker-compose.prod.yml")
        assert [name for name, _ in dev] == ["plugin-runner", "python-ai", "python-ai-worker"], dev
        assert [name for name, _ in prod] == ["plugin-runner", "python-ai"], prod
        for name, tz in dev + prod:
            assert tz == "UTC", f"compose 的服务 {name} 的 TZ={tz}"


class TestGateFlagsDrift:
    def test_bare_naive_now_is_red(self, tmp_path):
        module = _repo_fixture(tmp_path)
        _add_app_file(
            tmp_path,
            "slower.py",
            "from datetime import datetime\n\n\ndef stamp():\n    return datetime.now()\n",
        )
        module.check_python_clock_caliber()
        assert module.problems, "app/ 里出现零参 datetime.now() 时必须报红"
        assert "slower.py:5" in module.problems[0], module.problems[0]

    def test_utcnow_today_localtime_and_bare_fromtimestamp_are_red(self, tmp_path):
        module = _repo_fixture(tmp_path)
        _add_app_file(
            tmp_path,
            "shapes.py",
            "import time\nfrom datetime import date, datetime\n\n"
            "a = datetime.utcnow()\n"
            "b = date.today()\n"
            "c = time.localtime()\n"
            "d = datetime.fromtimestamp(1700000000)\n",
        )
        module.check_python_clock_caliber()
        assert module.problems, "四种裸本地读法都必须报红"
        reported = module.problems[0]
        for lineno in (4, 5, 6, 7):
            assert f"shapes.py:{lineno}" in reported, f"漏报第 {lineno} 行：{reported}"

    def test_explicit_utc_shapes_are_not_offenders(self, tmp_path):
        module = _repo_fixture(tmp_path)
        _add_app_file(
            tmp_path,
            "aware.py",
            "from datetime import UTC, datetime\n\n"
            "a = datetime.now(UTC)\n"
            "b = datetime.now(tz=UTC)\n"
            "c = datetime.fromtimestamp(1700000000, UTC)\n",
        )
        module.check_python_clock_caliber()
        assert not module.problems, f"显式 UTC 口径的写法被当成了违规：{module.problems}"

    def test_docstring_prose_is_not_an_offender(self, tmp_path):
        """说明文字里写 `datetime.now()` 不算违规——真仓库的 time_tool.py 正是这么写的。"""
        module = _repo_fixture(tmp_path)
        _add_app_file(tmp_path, "explained.py", DOCSTRING_ONLY_APP_FILE)
        module.check_python_clock_caliber()
        assert not module.problems, f"docstring 里的说明文字被当成了违规：{module.problems}"

    def test_missing_tz_on_a_workload_is_red(self, tmp_path):
        """未声明 ≠ 已钉住：TZ 整行消失必须被判为"随节点漂"。"""
        module = _repo_fixture(
            tmp_path,
            COMPOSE_DEV=DEV_COMPOSE.replace('      TZ: "UTC"\n      DEEPSEEK', "      DEEPSEEK"),
        )
        module.check_python_clock_caliber()
        assert module.problems, "dev compose 的 python-ai 没声明 TZ 时门禁不能默默通过"
        assert "python-ai 没有声明 TZ" in module.problems[0], module.problems[0]

    def test_non_utc_tz_is_red(self, tmp_path):
        module = _repo_fixture(
            tmp_path,
            COMPOSE_PROD=PROD_COMPOSE.replace('      TZ: "UTC"', '      TZ: "Asia/Shanghai"', 1),
        )
        module.check_python_clock_caliber()
        assert module.problems, "TZ 钉成别的口径时必须报红"
        assert "Asia/Shanghai" in module.problems[0], module.problems[0]

    def test_helm_values_tz_missing_is_red(self, tmp_path):
        module = _repo_fixture(
            tmp_path,
            HELM_VALUES=HELM_VALUES.replace('  tz: "UTC"\n  replicas', "  replicas"),
        )
        module.check_python_clock_caliber()
        assert module.problems, "values 里 pythonAi.tz 消失时必须报红"
        assert "pythonAi.tz 没有声明" in module.problems[0], module.problems[0]

    def test_helm_values_tz_drift_is_red(self, tmp_path):
        module = _repo_fixture(
            tmp_path,
            HELM_VALUES=HELM_VALUES.replace(
                'pluginRunner:\n  enabled: true\n  tz: "UTC"',
                'pluginRunner:\n  enabled: true\n  tz: "Europe/Berlin"',
            ),
        )
        module.check_python_clock_caliber()
        assert module.problems, "helm 的 pluginRunner.tz 不是 UTC 时必须报红"
        assert "Europe/Berlin" in module.problems[0], module.problems[0]

    def test_helm_two_roots_are_read_separately(self, tmp_path):
        """两个根都叫 tz：在全文件上取第一个会拿 pythonAi 的值顶替 pluginRunner，漂移就漏了。"""
        module = _repo_fixture(
            tmp_path,
            HELM_VALUES=HELM_VALUES.replace(
                'pluginRunner:\n  enabled: true\n  tz: "UTC"', 'pluginRunner:\n  enabled: true'
            ),
        )
        module.check_python_clock_caliber()
        assert module.problems, "pythonAi.tz 还在、pluginRunner.tz 没了，必须报红"
        assert "pluginRunner.tz 没有声明" in module.problems[0], module.problems[0]

    def test_values_key_nobody_reads_is_red(self, tmp_path):
        """第八十三批"模板读了一个不存在的键"的反向形态：键写了、模板没引用 = 死配置。"""
        module = _repo_fixture(
            tmp_path,
            HELM_PYTHON_TEMPLATE=HELM_PYTHON.replace(
                "            - name: TZ\n              value: {{ .Values.pythonAi.tz | quote }}\n", ""
            ),
        )
        module.check_python_clock_caliber()
        assert module.problems, "values 里的 pythonAi.tz 没人引用时必须报红"
        assert ".Values.pythonAi.tz" in module.problems[0], module.problems[0]

    def test_comment_text_is_not_taken_as_a_declaration(self, tmp_path):
        """说明文字里写 `TZ: "UTC"` 不算钉住（第八十四批同一口径）。"""
        module = _repo_fixture(
            tmp_path,
            COMPOSE_PROD=PROD_COMPOSE.replace(
                '  plugin-runner:\n    image: ghcr.io/xiaodu55/hfusionhub-plugin-runner:latest\n'
                '    environment:\n      TZ: "UTC"',
                '  plugin-runner:\n    image: ghcr.io/xiaodu55/hfusionhub-plugin-runner:latest\n'
                '    environment:\n      # 应当声明 TZ: "UTC"',
            ),
        )
        module.check_python_clock_caliber()
        assert module.problems, "注释里的 TZ 不能被当成声明"
        assert "plugin-runner 没有声明 TZ" in module.problems[0], module.problems[0]

    def test_renamed_image_marker_does_not_silence_the_gate(self, tmp_path):
        """工作负载改名后按标记认会一个不剩——门禁消失比门禁变红更安静，必须自己报红。"""
        module = _repo_fixture(
            tmp_path,
            COMPOSE_PROD=PROD_COMPOSE.replace("hfusionhub-python", "other-python").replace(
                "hfusionhub-plugin-runner", "other-runner"
            ),
        )
        module.check_python_clock_caliber()
        assert module.problems, "prod compose 认不出任何 python 工作负载时必须报红"
        assert "没认出任何 python 工作负载" in module.problems[0], module.problems[0]

    def test_missing_topology_file_is_red_not_skipped(self, tmp_path):
        module = _repo_fixture(tmp_path, COMPOSE_DEV=None, HELM_PLUGIN_RUNNER_TEMPLATE=None)
        module.check_python_clock_caliber()
        assert len(module.problems) >= 1, "拓扑文件缺失不能默默跳过（门禁消失形态）"
        joined = "\n".join(module.problems)
        assert "dev compose 缺失" in joined and "plugin-runner.yaml 缺失" in joined, joined
