"""写侧时钟口径：三张钟面必须是同一个 UTC，判定列不得读会话钟。

`DATETIME` 列存的是**字面墙钟**，谁写就用谁的钟：JVM 默认时区写 `LocalDateTime.now()`，
MySQL 的 `NOW()`/`CURRENT_TIMESTAMP` 默认值写**会话时区**的墙钟，Connector/J 再按
`serverTimezone` 解释时间戳。第九十六批在真库上实测过后果：同一行回收站记录，UTC 会话判
"未过期"、`+08:00` 会话判"过期"（`WriteClockCaliberTest` 留了红判据与日志）。

现在两件事必须同时成立：判定 SQL 读 `UTC_TIMESTAMP()`（会话挪不动它），写入侧的
JVM / MySQL 服务端 / JDBC 三处都声明成 UTC。任一处漏钉或改回别的口径，"判定用一套钟、
列里存另一套墙钟"就以新形式回来。本文件把 `scripts/static-checks.py` 的检查 13 钉住：
先证它对真仓库绿、并真的接进了默认全跑档，再逐条注入漂移证它会红。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"

DEV_COMPOSE = """services:
  mysql8:
    image: mysql:8.0.36
    command: ["--default-time-zone=+00:00"]
  java-backend:
    image: app:latest
    environment:
      SPRING_DATASOURCE_URL: jdbc:mysql://mysql8:3306/hfusionhub?useSSL=false&serverTimezone=UTC
      JAVA_TOOL_OPTIONS: -Duser.timezone=UTC
"""

PROD_COMPOSE = DEV_COMPOSE

HELM_VALUES = """mysql:
  defaultTimeZone: "+00:00"
javaBackend:
  javaToolOptions: "-Duser.timezone=UTC"
"""

HELM_JAVA = """            - name: SPRING_DATASOURCE_URL
              value: "jdbc:mysql://x:3306/db?serverTimezone=UTC"
            - name: JAVA_TOOL_OPTIONS
              value: {{ .Values.javaBackend.javaToolOptions | quote }}
"""

HELM_MYSQL = """          args: ["--default-time-zone={{ .Values.mysql.defaultTimeZone }}"]
"""

APP_YML = """spring:
  datasource:
    url: jdbc:mysql://localhost:3306/hfusionhub?useSSL=false&serverTimezone=UTC
"""


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_static_checks", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_fixture(tmp_path: Path, **overrides: str | None) -> object:
    """写一份"三源全 UTC"的最小仓库，再按需把某一面换成漂移值（None = 该面缺失）。"""
    texts = {
        "COMPOSE_DEV": DEV_COMPOSE,
        "COMPOSE_PROD": PROD_COMPOSE,
        "HELM_VALUES": HELM_VALUES,
        "HELM_JAVA_TEMPLATE": HELM_JAVA,
        "HELM_MYSQL_TEMPLATE": HELM_MYSQL,
        "APP_YML": APP_YML,
    }
    texts.update(overrides)
    module = _load_checker()
    for name, default in texts.items():
        target = tmp_path / name
        if default is None:
            continue
        target.write_text(default, encoding="utf-8")
        setattr(module, name, target)
    for name in ("JAVA_MAPPER_XML_DIR", "JAVA_MAIN_JAVA"):
        directory = tmp_path / name
        directory.mkdir(exist_ok=True)
        setattr(module, name, directory)
    module.problems.clear()
    return module


class TestGateOnTheRepo:
    def test_gate_passes_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--write-clock-caliber"],
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
        assert "--write-clock-caliber" in main_body
        all_mode = main_body[main_body.index("args = parser.parse_args()"):
                             main_body.index("if args.tenant_columns:")]
        assert all_mode.count("args.write_clock_caliber") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_write_clock_caliber()" in main_body

    def test_decision_sql_actually_reads_the_database_utc_clock(self):
        """判定处的正向声称：门禁只查了反向（不许 NOW()），这几行必须真的读 UTC 钟。

        逐条点名而不是"文件里出现过 UTC_TIMESTAMP()"：同一个文件里既有判定行也有
        resultMap/插入行，只数出现次数会放过"改了别处、判定处没改"的情形。
        """
        base = ROOT / "java-backend" / "src" / "main"
        sites = {
            "resources/mapper/AgentApprovalMapper.xml": [
                "expires_at &gt; UTC_TIMESTAMP()",
                "expires_at &lt;= UTC_TIMESTAMP()",
            ],
            "resources/mapper/PluginMapper.xml": [
                "circuit_open_until &lt; UTC_TIMESTAMP()",
                "circuit_open_until = DATE_ADD(UTC_TIMESTAMP(), INTERVAL #{cooldownMinutes} MINUTE)",
            ],
            "java/com/hfusionhub/controller/NotificationController.java": [
                "sn.expires_at > UTC_TIMESTAMP()",
            ],
            "java/com/hfusionhub/mapper/DocumentMapper.java": [
                "recycle_expires_at <= UTC_TIMESTAMP()",
            ],
            "java/com/hfusionhub/mapper/KnowledgeBaseMapper.java": [
                "recycle_expires_at <= UTC_TIMESTAMP()",
            ],
            "java/com/hfusionhub/mapper/PromptTemplateMapper.java": [
                "recycle_expires_at <= UTC_TIMESTAMP()",
            ],
        }
        for rel, expected in sites.items():
            text = (base / rel).read_text(encoding="utf-8")
            for fragment in expected:
                assert fragment in text, f"{rel} 里的判定行没读库的 UTC 钟：{fragment}"


class TestGateFlagsDrift:
    def test_non_utc_jdbc_timezone_is_red(self, tmp_path):
        module = _repo_fixture(
            tmp_path,
            COMPOSE_PROD=PROD_COMPOSE.replace("serverTimezone=UTC", "serverTimezone=Asia/Shanghai"),
        )
        module.check_write_clock_caliber()
        assert module.problems, "prod compose 的 JDBC 口径改回 Asia/Shanghai 时门禁必须报红"
        assert "Asia/Shanghai" in module.problems[0]

    def test_non_utc_jvm_timezone_is_red(self, tmp_path):
        module = _repo_fixture(
            tmp_path,
            COMPOSE_DEV=DEV_COMPOSE.replace("-Duser.timezone=UTC", "-Duser.timezone=Asia/Shanghai"),
        )
        module.check_write_clock_caliber()
        assert module.problems, "JVM 默认时区不是 UTC 时必须报红（判定读 UTC、列里存 +8 墙钟）"
        assert "Asia/Shanghai" in module.problems[0]

    def test_missing_jvm_pin_is_red(self, tmp_path):
        """未声明 ≠ 已钉住：JAVA_TOOL_OPTIONS 整行消失必须被判为"随宿主漂"。"""
        module = _repo_fixture(
            tmp_path,
            COMPOSE_DEV=DEV_COMPOSE.replace(
                "      JAVA_TOOL_OPTIONS: -Duser.timezone=UTC\n", ""
            ),
        )
        module.check_write_clock_caliber()
        assert module.problems, "JVM 时区没声明时门禁不能默默通过"
        assert "没有声明" in module.problems[0]

    def test_values_key_nobody_reads_is_red(self, tmp_path):
        """第八十三批"模板读了一个不存在的键"的反向形态：键写了、模板没引用 = 死配置。"""
        module = _repo_fixture(tmp_path, HELM_MYSQL_TEMPLATE="          image: mysql:8.0\n")
        module.check_write_clock_caliber()
        assert module.problems, "values 里的 defaultTimeZone 没人引用时必须报红"
        assert ".Values.mysql.defaultTimeZone" in module.problems[0]

    def test_decision_column_read_with_session_clock_is_red(self, tmp_path):
        module = _repo_fixture(tmp_path)
        (tmp_path / "JAVA_MAPPER_XML_DIR" / "DocumentMapper.xml").write_text(
            "<select>AND recycle_expires_at &lt;= NOW()</select>\n", encoding="utf-8"
        )
        module.check_write_clock_caliber()
        assert module.problems, "判定列比较式里出现会话钟 NOW() 时必须报红"
        assert "NOW()" in module.problems[0]
        assert "DocumentMapper.xml:1" in module.problems[0]

    def test_prose_about_the_session_clock_is_not_an_offender(self, tmp_path):
        """说明文字里的 `NOW()` 不算违规——真仓库的 mapper 注释正是这么写的。

        不剥注释的门禁会在"解释为什么不用 NOW()"的注释上判红，而这种红会让人去删注释
        而不是去修代码，比没有门禁更糟。
        """
        module = _repo_fixture(tmp_path)
        (tmp_path / "JAVA_MAPPER_XML_DIR" / "AgentApprovalMapper.xml").write_text(
            "<!-- expires_at 用 JVM 墙钟写，判定却用 NOW()，两套钟 -->\n"
            "<select>AND expires_at &gt; UTC_TIMESTAMP()</select>\n",
            encoding="utf-8",
        )
        (tmp_path / "JAVA_MAIN_JAVA" / "Notice.java").write_text(
            "// 这里不用 NOW()，因为它取会话时区\npublic class Notice {}\n", encoding="utf-8"
        )
        module.check_write_clock_caliber()
        assert not module.problems, f"注释里的说明文字被当成了违规：{module.problems}"

    def test_reported_line_number_points_at_the_offending_line(self, tmp_path):
        """剥注释必须保留行数，否则报告里的行号会指错地方。"""
        module = _repo_fixture(tmp_path)
        (tmp_path / "JAVA_MAPPER_XML_DIR" / "DocumentMapper.xml").write_text(
            "<!-- 为什么不用 NOW()：它取会话钟 -->\n\n<select>AND expires_at &lt;= NOW()</select>\n",
            encoding="utf-8",
        )
        module.check_write_clock_caliber()
        assert module.problems, "判定列读 NOW() 必须报红"
        assert "DocumentMapper.xml:3" in module.problems[0], module.problems[0]

    def test_comment_text_is_not_taken_as_a_declaration(self, tmp_path):
        """说明文字里写 `-Duser.timezone=UTC` 不算钉住（第八十四批同一口径）。"""
        module = _repo_fixture(
            tmp_path,
            COMPOSE_DEV=DEV_COMPOSE.replace(
                "      JAVA_TOOL_OPTIONS: -Duser.timezone=UTC\n",
                "      # 应当由 JAVA_TOOL_OPTIONS 提供 -Duser.timezone=UTC\n",
            ),
        )
        module.check_write_clock_caliber()
        assert module.problems, "注释里的时钟写法不能被当成声明"
        assert "没有声明" in module.problems[0]
