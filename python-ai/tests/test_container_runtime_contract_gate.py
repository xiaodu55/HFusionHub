r"""检查 18 的门：compose 写下的运行期承诺，容器里必须真有对应实体。

第一百零九批第一次把 fullstack 整栈（含 mysql/redis/milvus）跑起来，量到两处"配置写了、
实体不存在"的断链，两处都不会让任何一步变红：

  ① `python-ai-worker` 的 command 是 `python -m arq arq_worker.WorkerSettings`，
     而改前的 deploy/Dockerfile.python 只 `COPY app/ app/` ⇒ 容器内
     `ModuleNotFoundError: No module named 'arq_worker'`，RestartCount 涨到 14；
     后果在队列侧——`arq:queue` 里那条 job 滞留 83.69s 无人消费，而 python-ai 的
     API 日志正常写着 "dispatched via arq"，健康检查全程 green。
  ② dev compose 的 redis7 以 `--requirepass "$REDIS_PASSWORD"` 启动，java-backend 只给了
     `SPRING_DATA_REDIS_HOST` ⇒ 登录接口 500 `RedisConnectionFailureException`
     （traceId 40bb29cf73464ff28f01caa37cbb40b8）。prod compose 同一段一直是成对的
     （deploy/docker-compose.prod.yml:176），所以这条只在整栈上才暴露。
  ③ application.yml 的 `python-ai.base-url` / `python-ai.engine.url` 是裸字面量
     `http://localhost:9000`，而三档拓扑只设 `AI_SERVICE_URL` ⇒ 容器里 java 调 python 的解析
     请求打到 java 自己身上（POST /api/document/204/parse → 400 I/O error，
     traceId 9dae81714a9a41a1812c0cb3155fca89）。
  ④ worker 继承了 deploy/Dockerfile.python 里给 uvicorn 写的 HEALTHCHECK（:9000）⇒ 容器
     running、心跳键在写，状态却永久 unhealthy（实测 probe_http=000、curl exit=7），
     真正要看的崩溃循环被这片假红盖住。

本文件钉住：真仓库绿、并进默认全跑档、每种历史坏形状注入时都红、以及两条"形状对了但
指向别处"的语义面（密码键引用的是 redis 自己用的那个变量、COPY 的源真在构建上下文里）。
"""

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"
DEV_COMPOSE = ROOT / "docker" / "docker-compose.yml"
PROD_COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"
DOCKERFILE_PYTHON = ROOT / "deploy" / "Dockerfile.python"
APP_YML = ROOT / "java-backend" / "src" / "main" / "resources" / "application.yml"

DEV_LABEL = "docker/docker-compose.yml"
PROD_LABEL = "deploy/docker-compose.prod.yml"

WORKER_COMMAND = 'command: ["python", "-m", "arq", "arq_worker.WorkerSettings"]'


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_container_contract_gate", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WORKER_HEALTH_BLOCKS = {
    "disable": "    healthcheck:\n      disable: true\n",
    "http": '    healthcheck:\n      test: ["CMD", "curl", "-f", "http://localhost:9000/health"]\n',
    "heartbeat": (
        '    healthcheck:\n'
        '      test: ["CMD-SHELL", "redis-cli -h redis7 -a \\"$REDIS_PASSWORD\\" --no-auth-warning'
        ' hexists arq:queue:health-check $(hostname) | grep -q 1"]\n'
    ),
    None: "",
}


def _dev_compose(
    worker_command: str,
    *,
    with_password: bool = True,
    worker_health: str | None = "disable",
) -> str:
    env = ["      SPRING_DATA_REDIS_HOST: redis7"]
    if with_password:
        env.append("      SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD:-}")
    env.append("      AI_SERVICE_URL: http://python-ai:9000")
    health = WORKER_HEALTH_BLOCKS[worker_health]
    return (
        "services:\n"
        "  redis7:\n"
        "    image: redis:7.2-alpine\n"
        "    environment:\n"
        "      REDIS_PASSWORD: ${REDIS_PASSWORD:-}\n"
        '    command: ["sh", "-c", '
        '"redis-server /usr/local/etc/redis/redis.conf --requirepass \\"$REDIS_PASSWORD\\""]\n'
        "  java-backend:\n"
        "    image: local/hfusionhub-java:fixture\n"
        "    build:\n"
        "      context: ../java-backend\n"
        "      dockerfile: ../deploy/Dockerfile.java\n"
        "    environment:\n" + "\n".join(env) + "\n"
        "  python-ai-worker:\n"
        "    image: local/hfusionhub-python:fixture\n"
        "    build:\n"
        "      context: ../python-ai\n"
        "      dockerfile: ../deploy/Dockerfile.python\n"
        f"    {worker_command}\n" + health
    )


PROD_COMPOSE_FIXTURE = (
    "services:\n"
    "  redis7:\n"
    "    image: redis:7.2-alpine\n"
    '    command: ["sh", "-c", "redis-server --requirepass \\"$REDIS_PASSWORD\\""]\n'
    "  java-backend:\n"
    "    image: local/hfusionhub-java:fixture\n"
    "    environment:\n"
    "      SPRING_DATA_REDIS_HOST: redis7\n"
    "      SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD:-}\n"
    "      AI_SERVICE_URL: http://python-ai:9000\n"
)

DOCKERFILE_FIXTURE = """FROM python:3.11-slim AS base
WORKDIR /app
RUN pip install --no-cache-dir "arq==0.26.3"
COPY requirements.txt .
COPY app/ app/
COPY arq_worker.py .
RUN mkdir -p /data/uploads
EXPOSE 9000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \\
    CMD curl -f http://localhost:9000/health || exit 1
USER hfusionhub
CMD ["python", "-m", "app.main"]
"""


def _fixture(
    tmp_path: Path,
    *,
    compose: str | None = None,
    dockerfile: str | None = None,
    worker_file: bool = True,
) -> object:
    """一份四条规则都成立的仓库，再按需把某一边改坏。"""
    module = _load_checker()
    (tmp_path / "docker").mkdir()
    (tmp_path / "deploy").mkdir()
    (tmp_path / "python-ai" / "app").mkdir(parents=True)
    dev = tmp_path / "docker" / "docker-compose.yml"
    dev.write_text(compose if compose is not None else _dev_compose(WORKER_COMMAND), encoding="utf-8")
    (tmp_path / "deploy" / "docker-compose.prod.yml").write_text(
        PROD_COMPOSE_FIXTURE, encoding="utf-8"
    )
    (tmp_path / "deploy" / "Dockerfile.python").write_text(
        dockerfile if dockerfile is not None else DOCKERFILE_FIXTURE, encoding="utf-8"
    )
    (tmp_path / "python-ai" / "requirements.txt").write_text("arq==0.26.3\n", encoding="utf-8")
    if worker_file:
        (tmp_path / "python-ai" / "arq_worker.py").write_text(
            "from app.core.tasks.arq_tasks import WorkerSettings  # noqa: F401\n", encoding="utf-8"
        )
    module.COMPOSE_TOPOLOGIES = (
        (DEV_LABEL, dev),
        (PROD_LABEL, tmp_path / "deploy" / "docker-compose.prod.yml"),
    )
    module.problems.clear()
    return module


FAKE_JAVA = """public class PythonAiClient {
    @Value("${python-ai.base-url:http://localhost:9000}")
    private String baseUrl;

    @Value("${python-ai.engine.url:http://localhost:9000}")
    private String engineUrl;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String serviceUrl;
}
"""

FAKE_APP_YML = """python-ai:
  base-url: ${AI_SERVICE_URL:http://localhost:9000}
  engine:
    url: ${AI_SERVICE_URL:http://localhost:9000}
ai-service:
  base-url: ${AI_SERVICE_URL:http://localhost:9000}
"""

FAKE_HELM_JAVA = """        - name: AI_SERVICE_URL
          value: http://python-ai:9000
"""


def _url_fixture(
    tmp_path: Path,
    *,
    app_yml: str | None = None,
    java: str | None = None,
    helm: str | None = None,
) -> object:
    """规则③的仓库：java 侧 3 处 @Value、application.yml 三个键、三档拓扑各设一次共享变量。

    `PYTHON_BASE_URL_MIN_SITES` 在真仓库是 10，这里按 fixture 的位点数下调，测的才是配对
    规则本身而不是下界数字。
    """
    module = _fixture(tmp_path)
    java_root = tmp_path / "java-fixture"
    java_root.mkdir()
    (java_root / "PythonAiClient.java").write_text(
        java if java is not None else FAKE_JAVA, encoding="utf-8"
    )
    app = tmp_path / "application.yml"
    app.write_text(app_yml if app_yml is not None else FAKE_APP_YML, encoding="utf-8")
    helm_path = tmp_path / "java-helm.yaml"
    helm_path.write_text(helm if helm is not None else FAKE_HELM_JAVA, encoding="utf-8")
    module.JAVA_MAIN_JAVA = java_root
    module.APP_YML = app
    module.PYTHON_BASE_URL_MIN_SITES = 3
    module.PYTHON_BASE_URL_MIN_PROPERTIES = 3
    module.PYTHON_BASE_URL_TOPOLOGIES = (
        (DEV_LABEL, module.COMPOSE_TOPOLOGIES[0][1], "java-backend"),
        (PROD_LABEL, module.COMPOSE_TOPOLOGIES[1][1], "java-backend"),
        ("deploy/helm/hfusionhub/templates/java.yaml", helm_path, None),
    )
    module.problems.clear()
    return module


def _worker_offenders(module) -> tuple[list[str], int]:
    return module._worker_module_offenders()


def _health_offenders(module) -> tuple[list[str], int]:
    return module._worker_health_offenders()


def _url_offenders(module) -> tuple[list[str], int]:
    return module._python_base_url_offenders()


def _auth_offenders(module) -> tuple[list[str], int]:
    return module._redis_auth_offenders()


def _env_of(path: Path, service: str) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc["services"][service]["environment"]


class TestGateOnTheRepo:
    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--container-runtime-contract"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            # 子进程默认跟随 Windows 控制台码页，中文 [ok] 行会把 reader 线程解码打挂
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_gate_is_in_the_default_all_mode(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()") :]
        assert "--container-runtime-contract" in main_body
        all_mode = main_body[
            main_body.index("args = parser.parse_args()") : main_body.index("if args.tenant_columns:")
        ]
        assert all_mode.count("args.container_runtime_contract") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_container_runtime_contract()" in main_body

    def test_repo_applicability_is_the_measured_shape(self):
        """适用面本身：1 处 arq worker 命令（dev）、2 个连 requirepass redis 的 java 工作负载、
        1 个 worker 的存活面、10 处 java→python 出站地址。"""
        module = _load_checker()
        worker_offenders, worker_commands = _worker_offenders(module)
        auth_offenders, auth_clients = _auth_offenders(module)
        health_offenders, health_checked = _health_offenders(module)
        url_offenders, url_sites = _url_offenders(module)
        assert worker_offenders == [], "\n".join(worker_offenders)
        assert auth_offenders == [], "\n".join(auth_offenders)
        assert health_offenders == [], "\n".join(health_offenders)
        assert url_offenders == [], "\n".join(url_offenders)
        assert worker_commands == 1, f"`python -m arq` 命令数应为 1，实际 {worker_commands}"
        assert auth_clients == 2, f"requirepass 拓扑下的 redis 客户端数应为 2，实际 {auth_clients}"
        assert health_checked == 1, f"worker 存活面应为 1，实际 {health_checked}"
        assert url_sites == 10, f"java→python 出站地址位点应为 10，实际 {url_sites}"

    def test_worker_entry_module_is_a_real_reexport(self):
        """镜像里那个文件必须真的把 WorkerSettings 暴露出来，否则 arq 只会换个报错方式死。"""
        shim = (ROOT / "python-ai" / "arq_worker.py").read_text(encoding="utf-8")
        assert "WorkerSettings" in shim
        assert re.search(r"^(from|import)\s+\S*arq_tasks", shim, re.MULTILINE), shim

    def test_dev_compose_java_declares_the_redis_password_key(self):
        """第一百零九批 D1 的回归位：只给 host 的那半边必须已经补上。"""
        env = _env_of(DEV_COMPOSE, "java-backend")
        assert "SPRING_DATA_REDIS_HOST" in env
        assert {"SPRING_DATA_REDIS_PASSWORD", "REDIS_PASSWORD"} & env.keys(), (
            f"dev compose 的 java-backend 又只剩 host 了：{sorted(env)}"
        )

    def test_password_key_interpolates_the_variable_redis_uses(self):
        """形状对了但指向另一个密钥=照样连不上，而且文本门不会红，所以单独钉。"""
        redis_var = re.findall(
            r"\$\{([A-Z_]+)", _env_of(DEV_COMPOSE, "redis7")["REDIS_PASSWORD"]
        )
        for path in (DEV_COMPOSE, PROD_COMPOSE):
            value = _env_of(path, "java-backend")["SPRING_DATA_REDIS_PASSWORD"]
            assert re.findall(r"\$\{([A-Z_]+)", value) == redis_var, (
                f"{path.name}: redis 用 {redis_var}，java 的密码键却引用 {value}"
            )

    def test_dockerfile_copies_both_the_package_and_the_entry_module(self):
        module = _load_checker()
        names = module._image_top_level_names(DOCKERFILE_PYTHON)
        assert {"app", "arq_worker"} <= names, f"COPY 派生的顶层模块名少了东西：{sorted(names)}"


class TestCommandModuleRule:
    def test_missing_copy_line_is_red(self, tmp_path):
        """D2 的历史形状：command 引用顶层模块，Dockerfile 只 COPY 了 app/。"""
        module = _fixture(
            tmp_path, dockerfile=DOCKERFILE_FIXTURE.replace("COPY arq_worker.py .\n", "")
        )
        offenders, commands = _worker_offenders(module)
        assert commands == 1, "适用面还在——服务没被删，只是镜像里没有那个模块"
        assert any("ModuleNotFoundError" in o and "arq_worker" in o for o in offenders), offenders

    def test_copy_to_a_non_root_destination_is_red(self, tmp_path):
        """`COPY arq_worker.py src/` 形状对了但不在 WORKDIR 上：顶层 import 仍然失败。"""
        module = _fixture(
            tmp_path, dockerfile=DOCKERFILE_FIXTURE.replace("COPY arq_worker.py .", "COPY arq_worker.py src/")
        )
        offenders, commands = _worker_offenders(module)
        assert commands == 1 and offenders, offenders

    def test_copy_source_absent_from_context_is_red(self, tmp_path):
        """COPY 写了但构建上下文里没有该文件：镜像里必然没有，且构建本身也会死。"""
        module = _fixture(tmp_path, worker_file=False)
        offenders, commands = _worker_offenders(module)
        assert commands == 1
        assert any("构建上下文里没有" in o for o in offenders), offenders

    def test_deleting_the_worker_service_is_red(self, tmp_path):
        """处置不得退化成"把崩的那个服务删掉"——计数按拓扑钉住了这条路。"""
        module = _fixture(tmp_path, compose=_dev_compose(WORKER_COMMAND).split("  python-ai-worker:")[0])
        offenders, commands = _worker_offenders(module)
        assert commands == 0
        assert any("worker 服务数 = 0，预期 1" in o for o in offenders), offenders

    def test_settings_attr_rename_is_a_shape_problem(self, tmp_path):
        module = _fixture(tmp_path, compose=_dev_compose(
            'command: ["python", "-m", "arq", "arq_worker.WorkerSetting"]'))
        offenders, commands = _worker_offenders(module)
        assert commands == 1, "服务还在，适用面不该漂走"
        assert any("不是 `<模块>.WorkerSettings` 形状" in o for o in offenders), offenders
        assert any("-m arq" in o for o in offenders) or any("入口参数" in o for o in offenders), offenders

    def test_command_without_build_is_red(self, tmp_path):
        """只有 image: 的 worker 无从核对镜像内容——静默跳过等于门消失。"""
        compose = _dev_compose(WORKER_COMMAND).replace(
            '  python-ai-worker:\n    image: local/hfusionhub-python:fixture\n'
            "    build:\n      context: ../python-ai\n"
            "      dockerfile: ../deploy/Dockerfile.python\n",
            '  python-ai-worker:\n    image: local/hfusionhub-python:fixture\n',
        )
        module = _fixture(tmp_path, compose=compose)
        offenders, commands = _worker_offenders(module)
        assert commands == 1
        assert any("没有 build.context" in o for o in offenders), offenders

    def test_block_style_command_parses_like_flow_style(self, tmp_path):
        """两种 YAML 写法都得认，否则把 flow 列表改成短横列表就绕过了门。"""
        module = _load_checker()
        block = '    command:\n      - "python"\n      - "-m"\n      - "arq"\n      - arq_worker.WorkerSettings\n'
        assert module._command_tokens(block) == ["python", "-m", "arq", "arq_worker.WorkerSettings"]
        assert module._arq_entry_module(module._command_tokens(block)) == ("arq_worker", None)

    def test_parsed_command_matches_yaml_on_the_repo(self):
        """解析器反空转：它读到的 command 必须与 PyYAML 的一致。"""
        module = _load_checker()
        doc = yaml.safe_load(DEV_COMPOSE.read_text(encoding="utf-8"))
        want = doc["services"]["python-ai-worker"]["command"]
        block = module._compose_service_blocks(DEV_COMPOSE.read_text(encoding="utf-8"))["python-ai-worker"]
        assert module._command_tokens(block) == want
        assert module._arq_entry_module(want) == ("arq_worker", None)


class TestRedisAuthRule:
    def test_missing_password_key_is_red(self, tmp_path):
        """D1 的历史形状：redis 起 requirepass，java 只给 host。"""
        module = _fixture(tmp_path, compose=_dev_compose(WORKER_COMMAND, with_password=False))
        offenders, clients = _auth_offenders(module)
        assert clients == 2, "适用面还在——客户端服务没被删，只是配对断了"
        assert any("java-backend" in o and "SPRING_DATA_REDIS_PASSWORD" in o for o in offenders), offenders

    def test_fallback_key_alone_counts_as_paired(self, tmp_path):
        """application.yml 的回退链是 ${SPRING_DATA_REDIS_PASSWORD:${REDIS_PASSWORD:}}，
        只给后者同样是成对声明——门不能把真实可用的配置判成违规。"""
        module = _fixture(tmp_path)
        dev = module.COMPOSE_TOPOLOGIES[0][1]
        text = dev.read_text(encoding="utf-8").replace(
            "      SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD:-}",
            "      REDIS_PASSWORD: ${REDIS_PASSWORD:-}",
        )
        dev.write_text(text, encoding="utf-8")
        offenders, clients = _auth_offenders(module)
        assert clients == 2 and offenders == [], offenders

    def test_dropping_requirepass_everywhere_is_red_not_green(self, tmp_path):
        """适用面为空本身判红：去掉密码不会让"配对"这件事自动成立。"""
        module = _fixture(tmp_path)
        for _, path in module.COMPOSE_TOPOLOGIES:
            path.write_text(
                path.read_text(encoding="utf-8").replace("--requirepass", "--maxmemory"),
                encoding="utf-8",
            )
        offenders, clients = _auth_offenders(module)
        assert clients == 0
        assert any("规则②的适用面为空" in o for o in offenders), offenders

    def test_host_key_rename_is_count_drift_red(self, tmp_path):
        module = _fixture(tmp_path)
        dev = module.COMPOSE_TOPOLOGIES[0][1]
        dev.write_text(
            dev.read_text(encoding="utf-8").replace(
                "      SPRING_DATA_REDIS_HOST: redis7", "      SPRING_DATA_REDIS_URL: redis7"
            ),
            encoding="utf-8",
        )
        offenders, _ = _auth_offenders(module)
        assert any("工作负载数 = 0，预期 1" in o for o in offenders), offenders

    def test_check_appends_problems_not_print_pass(self, tmp_path):
        module = _fixture(tmp_path, compose=_dev_compose(WORKER_COMMAND, with_password=False))
        module.check_container_runtime_contract()
        assert module.problems, "有违规时 problems 必须非空，否则这条门是空的"

    def test_helm_redis_stays_out_of_the_rule_until_it_has_auth(self):
        """本批核对：helm 的 redis 不起 requirepass，java.yaml 只需 host。
        若哪天给它上了密码，这条会红——那时必须把该拓扑并进扫描清单，不能靠门默许。"""
        chart = ROOT / "deploy" / "helm" / "hfusionhub" / "templates"
        redis = (chart / "redis.yaml").read_text(encoding="utf-8")
        assert "--requirepass" not in redis, (
            "helm 的 redis 开始要密码了：把 helm 拓扑并进检查 18 规则②的扫描清单再改这条断言"
        )
        java = (chart / "java.yaml").read_text(encoding="utf-8")
        assert "SPRING_DATA_REDIS_HOST" in java


class TestBaseUrlRule:
    def test_one_variable_across_three_topologies_is_green(self, tmp_path):
        module = _url_fixture(tmp_path)
        offenders, sites = _url_offenders(module)
        assert sites == 3, f"出站位点数应为 3，实际 {sites}"
        assert offenders == [], "\n".join(offenders)

    def test_bare_literal_is_red(self, tmp_path):
        """D4 的历史形状：键在 yml 里写死 http://localhost:9000，拓扑改不动。"""
        module = _url_fixture(
            tmp_path,
            app_yml=FAKE_APP_YML.replace(
                "  base-url: ${AI_SERVICE_URL:http://localhost:9000}\n  engine:",
                "  base-url: http://localhost:9000\n  engine:",
            ),
        )
        offenders, sites = _url_offenders(module)
        assert sites == 3, "适用面还在——位点没删，只是来源变成了字面量"
        assert any("python-ai.base-url" in o and "裸字面量" in o for o in offenders), offenders

    def test_properties_splitting_into_two_variables_is_red(self, tmp_path):
        """键名不同没关系，来源必须只有一个：两个变量时拓扑只设其一就静默留回宿主地址。"""
        module = _url_fixture(
            tmp_path,
            app_yml=FAKE_APP_YML.replace(
                "python-ai:\n  base-url: ${AI_SERVICE_URL", "python-ai:\n  base-url: ${PYTHON_AI_BASE_URL", 1
            ),
        )
        offenders, _ = _url_offenders(module)
        assert any("不同的环境变量" in o for o in offenders), offenders

    def test_property_missing_from_yml_is_red(self, tmp_path):
        """yml 里没有这个键时，@Value 只能吃代码缺省值，而缺省值是宿主地址。"""
        module = _url_fixture(
            tmp_path,
            app_yml=FAKE_APP_YML.replace(
                "  base-url: ${AI_SERVICE_URL:http://localhost:9000}\n  engine:", "  engine:"
            ),
        )
        offenders, _ = _url_offenders(module)
        assert any("application.yml 里没有 python-ai.base-url" in o for o in offenders), offenders

    def test_topology_without_the_shared_variable_is_red(self, tmp_path):
        module = _url_fixture(tmp_path)
        dev = module.COMPOSE_TOPOLOGIES[0][1]
        dev.write_text(
            dev.read_text(encoding="utf-8").replace(
                "      AI_SERVICE_URL: http://python-ai:9000\n", ""
            ),
            encoding="utf-8",
        )
        offenders, _ = _url_offenders(module)
        assert any(
            "java 工作负载没有声明 AI_SERVICE_URL" in o and DEV_LABEL in o for o in offenders
        ), offenders

    def test_helm_template_without_the_shared_variable_is_red(self, tmp_path):
        module = _url_fixture(tmp_path, helm="        - name: OTHER_KEY\n          value: 1\n")
        offenders, _ = _url_offenders(module)
        assert any(
            "java 工作负载没有声明 AI_SERVICE_URL" in o and "helm" in o for o in offenders
        ), offenders

    def test_renaming_the_whole_property_family_is_red(self, tmp_path):
        """java 侧不再有 :9000 缺省的 @Value = 规则③扫描不到任何东西，适用面为空本身判红。"""
        module = _url_fixture(tmp_path, java="public class PythonAiClient {\n    private String url;\n}\n")
        offenders, sites = _url_offenders(module)
        assert sites == 0
        assert any("规则③的适用面为空" in o for o in offenders), offenders

    def test_shrinking_the_site_count_is_red(self, tmp_path):
        module = _url_fixture(
            tmp_path,
            java="""public class PythonAiClient {
    @Value("${python-ai.base-url:http://localhost:9000}")
    private String baseUrl;

    @Value("${python-ai.engine.url:http://localhost:9000}")
    private String engineUrl;
}
""",
        )
        offenders, sites = _url_offenders(module)
        assert sites == 2
        assert any("规则③的适用面缩小了" in o for o in offenders), offenders

    def test_repo_outbound_urls_share_the_ai_service_url_variable(self):
        """第一百零九批 D4 的回归位：三个键都吃 AI_SERVICE_URL，宿主缺省值只在冒号之后。"""
        flat = _load_checker()._flatten_yaml_scalars(APP_YML.read_text(encoding="utf-8"))
        shared = set()
        for prop in ("python-ai.base-url", "python-ai.engine.url", "ai-service.base-url"):
            value = flat.get(prop)
            assert value is not None, f"application.yml 丢了 {prop}"
            matched = re.match(r"^\$\{(AI_SERVICE_URL):([^}]*)\}$", value or "")
            assert matched is not None, f"{prop} = {value!r} 不再是 ${{AI_SERVICE_URL:...}} 形状"
            shared.add(matched.group(1))
        assert shared == {"AI_SERVICE_URL"}

    def test_check_appends_problems_when_the_url_rule_breaks(self, tmp_path):
        module = _url_fixture(
            tmp_path,
            app_yml=FAKE_APP_YML.replace("  base-url: ${AI_SERVICE_URL", "  base-url: AI_SERVICE_URL", 1),
        )
        module.check_container_runtime_contract()
        assert any("出站地址" in p or "裸字面量" in p for p in module.problems), module.problems


class TestWorkerHealthRule:
    def test_inheriting_the_http_probe_is_red(self, tmp_path):
        """D3 的历史形状：worker 块不写 healthcheck，于是继承镜像里给 :9000 写的探针。"""
        module = _fixture(tmp_path, compose=_dev_compose(WORKER_COMMAND, worker_health=None))
        offenders, checked = _health_offenders(module)
        assert checked == 1, "适用面还在——worker 服务没被删，只是探针没换"
        assert any("继承镜像" in o and ":9000" in o for o in offenders), offenders

    def test_disable_is_green(self, tmp_path):
        module = _fixture(tmp_path)
        offenders, checked = _health_offenders(module)
        assert checked == 1 and offenders == [], offenders

    def test_custom_probe_still_hitting_the_service_port_is_red(self, tmp_path):
        """自己写探针但照着 API 抄，照样打 :9000——门不能被"有 healthcheck 键"骗过去。"""
        module = _fixture(tmp_path, compose=_dev_compose(WORKER_COMMAND, worker_health="http"))
        offenders, checked = _health_offenders(module)
        assert checked == 1
        assert any("仍在打 :9000" in o for o in offenders), offenders

    def test_queue_heartbeat_probe_is_green(self, tmp_path):
        """换成真正的存活信号（队列心跳）就不再要求 disable。"""
        module = _fixture(tmp_path, compose=_dev_compose(WORKER_COMMAND, worker_health="heartbeat"))
        offenders, checked = _health_offenders(module)
        assert checked == 1 and offenders == [], offenders

    def test_deleting_the_worker_service_is_red_not_green(self, tmp_path):
        module = _fixture(
            tmp_path, compose=_dev_compose(WORKER_COMMAND).split("  python-ai-worker:")[0]
        )
        offenders, checked = _health_offenders(module)
        assert checked == 0
        assert any("规则④的适用面为空" in o for o in offenders), offenders

    def test_probe_port_only_comes_from_the_final_stage(self, tmp_path):
        """多阶段构建里 build 段的 HEALTHCHECK 不会带进运行阶段，端口得读对否则误判。"""
        module = _load_checker()
        staged = (
            "FROM python:3.11-slim AS build\n"
            "HEALTHCHECK CMD curl -f http://localhost:9000/health || exit 1\n"
            "FROM python:3.11-slim AS base\n"
            "WORKDIR /app\n"
            "COPY app/ app/\n"
        )
        path = tmp_path / "Dockerfile.staged"
        path.write_text(staged, encoding="utf-8")
        assert module._image_probe_port(path) is None
        assert module._image_probe_port(Path(DOCKERFILE_PYTHON)) == "9000"

    def test_repo_worker_disables_the_inherited_probe(self):
        """第一百零九批 D3 的回归位：dev compose 的 worker 必须显式关掉那个 HTTP 探针。"""
        doc = yaml.safe_load(DEV_COMPOSE.read_text(encoding="utf-8"))
        assert doc["services"]["python-ai-worker"].get("healthcheck") == {"disable": True}, (
            f"worker 的 healthcheck 又变回继承镜像了：{doc['services']['python-ai-worker']}"
        )


class TestYamlFlattenOracle:
    def test_flattened_paths_agree_with_pyyaml_on_the_repo_yml(self):
        """摊平器反空转：它读到的每个点号路径与值，PyYAML 必须给出同一个标量。

        规则③靠 `python-ai.engine.url` 这类嵌套键定位出站地址，摊平器把缩进算错就会
        既查不到真键、又凭空造出一个"存在"的路径。
        """
        raw = APP_YML.read_text(encoding="utf-8")
        flat = _load_checker()._flatten_yaml_scalars(raw)
        tree = yaml.safe_load(raw)

        def walk(node, prefix=""):
            out = {}
            if isinstance(node, dict):
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    if isinstance(value, dict):
                        out.update(walk(value, path))
                    elif isinstance(value, list):
                        # 摊平器按缩进认父，序列里的映射会被挂到序列键下面（无下标），
                        # oracle 必须同样处理，否则 `group-configs` 下的真实键算凭空造。
                        for item in value:
                            if isinstance(item, dict):
                                out.update(walk(item, path))
                    else:
                        out[path] = value
            return out

        tree_flat = walk(tree)
        for path, value in flat.items():
            assert path in tree_flat, f"摊平器凭空造出了 {path}（PyYAML 没有这个路径）"
            expected = tree_flat[path]
            if isinstance(expected, bool):
                expected = "true" if expected else "false"
            assert str(expected) == value, (
                f"{path}: PyYAML 读到 {expected!r}，摊平器读到 {value!r}"
            )
