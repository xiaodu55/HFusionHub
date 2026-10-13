r"""Flyway 在 CI 里的调用形状：连接信息必须走插件真读的那三个旗标。

第一百零八批量到的现行缺陷（不是假想）：`e2e.yml` 两处与 `eval-nightly.yml` 一处的
`Run Flyway migrations` 步骤把连接信息写进 `SPRING_DATASOURCE_*` 环境变量，命令行只有
`mvn --batch-mode flyway:migrate`。flyway-maven-plugin 不读 Spring 的键，于是每次都死在

    FlywayException: Unable to connect to the database. Configure the url, user and password!

（CI run 38233532705 的 e2e-full job 日志第 620 行；改动前后的同一行命令在活 MySQL 8.0.46
上各跑一遍，旧形状复现上面那句、新形状应用 87 条迁移并落到 v86。）

这类缺陷同样**不会让任何一步变红得可见**：步骤从诞生起就红，但如果没人看那个 job，
它就和"迁移已经跑过"长得一模一样。所以本文件钉住检查 17 的四件事——真仓库绿、
接进默认全跑档、注入每种历史形态时红、以及旗标值与本 job 的 service 凭据同源
（传了 `-Dflyway.user` 但指向另一个库，形状门同样是绿的）。
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"
WORKFLOWS = ROOT / ".github" / "workflows"
BS = "\\"

FLYWAY_FILES = ("ci.yml", "e2e.yml", "eval-nightly.yml")
EXPECTED_CALLS = {"ci.yml": 2, "e2e.yml": 2, "eval-nightly.yml": 1}
TOTAL_CALLS = sum(EXPECTED_CALLS.values())


def _flyway_step(goal: str = "migrate", *, form: str = "flags", name: str | None = None) -> str:
    """一个 flyway 步骤的几种写法：`flags` 是正确形状，其余都是历史上出现过的坏形状。"""
    label = name or f"Run Flyway {'migrations' if goal == 'migrate' else goal}"
    head = f"      - name: {label}\n        working-directory: java-backend\n"
    if form == "spring_only":
        return (
            head
            + "        env:\n"
            + "          SPRING_DATASOURCE_URL: jdbc:mysql://localhost:3306/hfusionhub\n"
            + "          SPRING_DATASOURCE_USERNAME: e2e\n"
            + "          SPRING_DATASOURCE_PASSWORD: e2e-pass\n"
            + f"        run: mvn --batch-mode flyway:{goal}\n"
        )
    body = (
        f"          mvn --batch-mode flyway:{goal} {BS}\n"
        f"            -Dflyway.url=jdbc:mysql://localhost:3306/hfusionhub {BS}\n"
        f"            -Dflyway.user=e2e {BS}\n"
        "            -Dflyway.password=e2e-pass\n"
    )
    if form == "flags":
        return head + "        run: |\n" + body
    if form == "flags_plus_spring_env":
        return (
            head
            + "        env:\n"
            + "          SPRING_DATASOURCE_URL: jdbc:mysql://localhost:3306/hfusionhub\n"
            + "        run: |\n"
            + body
        )
    if form == "flags_soft":
        return head + "        continue-on-error: true\n" + "        run: |\n" + body
    if form == "renamed_goal":
        return head + "        run: |\n" + body.replace(f"flyway:{goal}", f"flyway:{goal}X")
    if form != "flags":
        raise ValueError(form)
    raise AssertionError("unreachable")


def _workflow(job: str, steps: str, *, with_service: bool = True) -> str:
    service = (
        "    services:\n      mysql:\n        image: mysql:8.0\n        env:\n"
        "          MYSQL_DATABASE: hfusionhub\n          MYSQL_USER: e2e\n"
        "          MYSQL_PASSWORD: e2e-pass\n"
        if with_service
        else ""
    )
    return (
        "name: fixture\non: push\njobs:\n"
        f"  {job}:\n    runs-on: ubuntu-latest\n"
        + service
        + "    steps:\n      - uses: actions/checkout@v4\n"
        + steps
    )


PINNED_POM = """<project>
    <build>
        <plugins>
            <plugin>
                <groupId>org.flywaydb</groupId>
                <artifactId>flyway-maven-plugin</artifactId>
                <version>${flyway.version}</version>
            </plugin>
        </plugins>
    </build>
</project>
"""


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_flyway_cli_gate", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(tmp_path: Path, *, steps: dict[str, str] | None = None, pom: str | None = None):
    """一份四门齐全、全部正确形状的仓库，再按需把某个 workflow 的正文或 pom 换掉。"""
    module = _load_checker()
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    defaults = {
        "ci.yml": _workflow("java", _flyway_step("migrate") + _flyway_step("info")),
        "e2e.yml": _workflow("e2e-full", _flyway_step() + _flyway_step()),
        "eval-nightly.yml": _workflow("eval", _flyway_step()),
        # 目录里必须还有别的 workflow：检查 17 扫全目录，噪声文件不参与计数
        "release.yml": _workflow("release", "      - run: echo release\n", with_service=False),
    }
    defaults.update(steps or {})
    for filename, text in defaults.items():
        (workflow_dir / filename).write_text(text, encoding="utf-8")

    java_dir = tmp_path / "java-backend"
    java_dir.mkdir()
    pom_path = java_dir / "pom.xml"
    pom_path.write_text(PINNED_POM if pom is None else pom, encoding="utf-8")

    module.WORKFLOW_DIR = workflow_dir
    module.JAVA_POM = pom_path
    module.problems.clear()
    return module


def _offenders(module) -> tuple[list[str], int]:
    return module._flyway_offenders(sorted(module.WORKFLOW_DIR.iterdir()))


def _real_steps(filename: str) -> list[dict]:
    doc = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
    return [
        step
        for job in doc["jobs"].values()
        for step in job.get("steps", [])
        if "flyway:" in str(step.get("run", ""))
    ]


class TestGateOnTheRepo:
    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--flyway-cli"],
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
        assert "--flyway-cli" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()"): main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.flyway_cli") >= 2, f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        assert "check_flyway_cli()" in main_body

    def test_the_repo_has_five_flyway_calls_and_no_offender(self):
        """正向声称：适用面非空，且每处的调用数按文件钉住（删步骤会在这里红）。"""
        module = _load_checker()
        offenders, calls = module._flyway_offenders(
            sorted(p for p in module.WORKFLOW_DIR.iterdir() if p.suffix == ".yml")
        )
        assert calls == TOTAL_CALLS, f"flyway 调用数应为 {TOTAL_CALLS}，实际 {calls}"
        assert offenders == [], "真仓库应当无违规：\n" + "\n".join(offenders)

    def test_every_site_passes_all_three_flags_and_no_spring_env(self):
        for filename in FLYWAY_FILES:
            steps = _real_steps(filename)
            assert len(steps) == EXPECTED_CALLS[filename], f"{filename} 的 flyway 步骤数变了"
            for step in steps:
                run = str(step["run"])
                for flag in ("-Dflyway.url=", "-Dflyway.user=", "-Dflyway.password="):
                    assert flag in run, f"{filename}:{step.get('name')} 缺 {flag}"
                env = step.get("env") or {}
                for key in ("SPRING_DATASOURCE_URL", "SPRING_DATASOURCE_USERNAME", "SPRING_DATASOURCE_PASSWORD"):
                    assert key not in env, f"{filename}:{step.get('name')} 还挂着空转的 {key}"
                assert step.get("continue-on-error") is not True, f"{filename}:{step.get('name')} 被软化成不红"


class TestFlagsMatchServiceCredentials:
    """旗标值与本 job 的 mysql service 同源——形状对了但库名/账号指错，文本门照样绿。"""

    def test_url_user_password_equal_the_declared_service_env(self):
        checked = 0
        for filename in FLYWAY_FILES:
            doc = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
            for job_name, job in doc["jobs"].items():
                service_env = (job.get("services") or {}).get("mysql", {}).get("env", {})
                if not all(service_env.get(key) for key in ("MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD")):
                    continue
                for step in job.get("steps", []):
                    run = str(step.get("run", ""))
                    if "flyway:" not in run:
                        continue
                    checked += 1
                    values = {
                        token.split("=", 1)[0]: token.split("=", 1)[1]
                        for token in run.replace(BS + "\n", "").replace("\n", " ").split()
                        if token.startswith("-Dflyway.") and "=" in token
                    }
                    assert values, f"{filename}:{job_name} 的 flyway 步骤没有 -Dflyway.* 旗标"
                    assert str(values.get("-Dflyway.url", "")).endswith("/" + service_env["MYSQL_DATABASE"]), (
                        f"{filename}:{job_name} 指向了 service 没建的库"
                    )
                    assert values.get("-Dflyway.user") == service_env["MYSQL_USER"], f"{filename}:{job_name}"
                    assert values.get("-Dflyway.password") == service_env["MYSQL_PASSWORD"], f"{filename}:{job_name}"
        assert checked == TOTAL_CALLS, f"只核对到 {checked} 处，预期 {TOTAL_CALLS}——服务声明或步骤被改名了"


class TestPluginPin:
    def test_pom_pins_the_plugin_by_property_reference(self):
        """钉的是引用不是字面量：数字常量会把同源关系复制成两处各自漂移。

        同源的另半边是 `flyway-core` 自己不带 `<version>`——它由父 BOM 的
        `flyway.version` 管理，所以插件写同一个引用就必然与运行时同版本。
        """
        module = _load_checker()
        assert module._flyway_plugin_pin_offenders() == []
        pom = (ROOT / "java-backend" / "pom.xml").read_text(encoding="utf-8")
        assert "<version>${flyway.version}</version>" in pom
        core = re.search(
            r"<dependency>\s*<groupId>org\.flywaydb</groupId>\s*"
            r"<artifactId>flyway-core</artifactId>(.*?)</dependency>",
            pom,
            re.S,
        )
        assert core is not None, "pom 里没有 flyway-core 依赖，${flyway.version} 就无从同源"
        assert "<version>" not in core.group(1), (
            "flyway-core 一旦被显式钉版，${flyway.version} 就不再是运行时的版本，同源保证失效"
        )

    def test_unpinned_pom_is_red(self, tmp_path):
        module = _fixture(tmp_path, pom=PINNED_POM.replace(
            "            <plugin>\n                <groupId>org.flywaydb</groupId>\n"
            "                <artifactId>flyway-maven-plugin</artifactId>\n"
            "                <version>${flyway.version}</version>\n            </plugin>\n", ""))
        offenders, _ = _offenders(module)
        assert any("没有声明 flyway-maven-plugin" in o for o in offenders), offenders

    def test_numeric_pinned_version_is_red(self, tmp_path):
        module = _fixture(tmp_path, pom=PINNED_POM.replace("${flyway.version}", "11.7.2"))
        offenders, _ = _offenders(module)
        assert any("不是 `${flyway.version}`" in o for o in offenders), offenders

    def test_plugin_without_version_is_red(self, tmp_path):
        module = _fixture(tmp_path, pom=PINNED_POM.replace("                <version>${flyway.version}</version>\n", ""))
        offenders, _ = _offenders(module)
        assert any("没有 <version>" in o for o in offenders), offenders

    def test_missing_pom_is_red(self, tmp_path):
        module = _fixture(tmp_path)
        module.JAVA_POM.unlink()
        offenders, _ = _offenders(module)
        assert any("缺失" in o for o in offenders), offenders


class TestGateFlagsDrift:
    def test_spring_only_site_is_red_on_both_rules(self, tmp_path):
        """历史形状：命令行没旗标 + env 里三个空转的键，两条都要红。"""
        module = _fixture(tmp_path, steps={"e2e.yml": _workflow(
            "e2e-full", _flyway_step(form="spring_only") + _flyway_step())})
        offenders, calls = _offenders(module)
        assert calls == TOTAL_CALLS, "适用面还在——步骤没被删，只是形状坏"
        missing = [o for o in offenders if "命令行缺" in o]
        dead = [o for o in offenders if "SPRING_DATASOURCE_URL" in o and "空转" in o]
        assert len(missing) == 1 and len(dead) == 1, offenders

    def test_correct_flags_plus_leftover_spring_env_is_red(self, tmp_path):
        module = _fixture(tmp_path, steps={"eval-nightly.yml": _workflow(
            "eval", _flyway_step(form="flags_plus_spring_env"))})
        offenders, _ = _offenders(module)
        assert len(offenders) == 1 and "空转的开关" in offenders[0], offenders

    def test_continue_on_error_is_red(self, tmp_path):
        module = _fixture(tmp_path, steps={"ci.yml": _workflow(
            "java", _flyway_step("migrate", form="flags_soft") + _flyway_step("info"))})
        offenders, _ = _offenders(module)
        assert any("迁移失败必须让 job 红" in o for o in offenders), offenders

    def test_deleting_a_site_is_red_not_green(self, tmp_path):
        """处置不得退化成"把红的那一步删掉"——计数按文件钉住了这条路。"""
        module = _fixture(tmp_path, steps={"e2e.yml": _workflow("e2e-full", _flyway_step())})
        offenders, calls = _offenders(module)
        assert calls == TOTAL_CALLS - 1
        assert any("e2e.yml 里 flyway 调用数是 1，预期 2" in o for o in offenders), offenders

    def test_renaming_the_goal_empties_the_applicability(self, tmp_path):
        """三个文件一起改名才是"门禁消失"形态：单点改名只会撞计数那条规则。"""
        module = _fixture(tmp_path, steps={
            "ci.yml": _workflow("java", _flyway_step("migrate", form="renamed_goal")
                                + _flyway_step("info", form="renamed_goal")),
            "e2e.yml": _workflow("e2e-full", _flyway_step(form="renamed_goal") + _flyway_step(form="renamed_goal")),
            "eval-nightly.yml": _workflow("eval", _flyway_step(form="renamed_goal")),
        })
        module.check_flyway_cli()
        text = "\n".join(module.problems)
        assert "适用面为空" in text, module.problems

    def test_check_reports_red_not_silent_pass(self, tmp_path):
        module = _fixture(tmp_path, steps={"e2e.yml": _workflow(
            "e2e-full", _flyway_step(form="spring_only") + _flyway_step())})
        module.check_flyway_cli()
        assert module.problems, "有违规时 problems 必须非空，否则门是空的"

    def test_missing_workflow_dir_is_red(self, tmp_path):
        module = _fixture(tmp_path)
        for path in module.WORKFLOW_DIR.iterdir():
            path.unlink()
        module.check_flyway_cli()
        assert any("没有 workflow 文件" in p for p in module.problems), module.problems


class TestStepParserIsNotBlind:
    """解析器本身的反空转：它读到的东西必须与 YAML 解析一致，否则门在查一个不存在的形状。"""

    def test_parsed_run_equals_yaml_run(self):
        module = _load_checker()
        for filename in FLYWAY_FILES:
            doc = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
            want = [str(s["run"]) for job in doc["jobs"].values() for s in job.get("steps", [])
                    if "flyway:" in str(s.get("run", ""))]
            got = [s["run"] for s in module._workflow_steps(WORKFLOWS / filename) if "flyway:" in s["run"]]
            assert len(got) == len(want), f"{filename} 的步骤切分漏了调用"
            for script, expected in zip(got, want):
                # 块标量正文里 shell 只看词边界，缩进不参与；按空白归一比较，
                # 这样"漏了一个参数"仍然会红，而"少两个空格"不会假红。
                assert " ".join(script.split()) == " ".join(expected.split()), (
                    f"{filename}: 解析出的脚本与 YAML 不一致\n{script!r}\n{expected!r}"
                )

    def test_parsed_names_are_not_empty(self):
        """名字为空会让违规报告指不出是哪一步—— `- name:` 那行的键在列表符后面。"""
        module = _load_checker()
        names = [s["name"] for filename in FLYWAY_FILES
                 for s in module._workflow_steps(WORKFLOWS / filename) if "flyway:" in s["run"]]
        assert len(names) == TOTAL_CALLS
        assert all(n for n in names), f"有步骤名解析成空：{names}"
