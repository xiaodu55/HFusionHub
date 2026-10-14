#!/usr/bin/env python3
"""static-checks.py — HFusionHub 静态一致性校验（CI 用，纯标准库）

检查 1：租户列完整性
  解析 db/migration/*.sql 中所有建表/加列语句，与
  MybatisPlusConfig.TENANT_IGNORE_TABLES 对比，找出"被租户拦截器过滤
  （不在忽略表）但没有 tenant_id 列"的表——这类表一旦被查询就会产生
  "Unknown column 'tenant_id'" SQL 错误（历史上 V52/V53 出过）。

检查 2：内部端点 token 键一致性
  扫描 controller/ 下所有 @Value("${...}") 注解，凡是变量名含
  internal-token 的，必须是 python-ai.internal-token（与其他内部端点一致）。

检查 3：测试计数文档同步
  静态统计三端测试数（Java @Test 注解、Python tests/ 下 def test_、
  前端 src/ 下 spec 的 it/test 单测数），与 README.md 徽章、AGENTS.md
  "Tests:" 行、CLAUDE.md 测试表比对。AGENTS.md 要求文档与代码计数保持
  同步，防止漂移。

检查 4：Flyway 版本窗口文档同步
  取 db/migration/ 下最新迁移版本 V<n>，校验 CLAUDE.md / AGENTS.md /
  README.md / docs/java-backend.md / docs/database.md 中的区间写法
  "V1–V<n>" 与新脚本窗口写法 "V<n+1>+" 是否与实际一致。

检查 5：H2 测试 schema 漂移防护（R15-22 收尾）
  解析 V1..V<latest> 迁移链得到最终表-列集合，与 schema-h2.sql 静态对比；
  漂移超出 scripts/h2_schema_drift_baseline.json 基线（即新增漂移）时
  报错，防止手维护的 H2 schema 与真实迁移继续漂移。

检查 6：当前态文档的声称-实现对账
  README 等当前态文档不得声称已移除/未实现的能力（如"图谱召回"）。

检查 7：Helm 模板引用的 .Values 根必须存在
  模板里的 `.Values.<root>` 必须在 values.yaml 顶层有定义。Go 模板对不存在的根取
  字段是执行期报错，`| default` 救不回来，整张 chart 渲染失败。

检查 8：容器运行身份三处同源
  deploy/Dockerfile.python 与 deploy/Dockerfile.java 用 -u/-g 钉死的 uid/gid，
  必须与 helm values.yaml 的 podSecurity.runAsUser/runAsGroup/fsGroup 是同一组号。
  卷能不能写取决于进程身份与卷属主是否对齐；未钉的 `-r`/`-S` 用户号由基镜像决定，
  重建即漂移，而 fsGroup 是另一处手写的数字，无人核对就会各说各话。

检查 9：Java↔Python 文档目录的路径契约
  Java 入库的 file_path 是它容器内的绝对路径（Dockerfile.java 运行阶段 WORKDIR +
  DocumentServiceImpl.UPLOAD_DIR），python 只能在自己的 DOCUMENT_STORAGE_ROOT 下读到它。
  每个部署面（dev compose / prod compose / helm）的 python 工作负载都必须"挂 uploads 卷 +
  设同号 root"成对出现，缺任一侧 Java→Python 的 /api/parse 就只会回 400。

检查 10：评测产物落点在卷上、且与共享根分面
  EVAL_HARNESS_DATA_DIR（runs/reports/scores）与 EVAL_JUDGE_CACHE_PATH 在每个 python
  工作负载上都要设成绝对路径、落在挂载点内，helm 侧还得是 ReadWriteMany PVC；缓存与共享
  根同目录时必须按 $(POD_NAME) 分面。产物是"写一次、按文件名读回"⇒ 该共享，judge 缓存是
  整文件 read-modify-write ⇒ 共享即互相覆盖，两条规则方向相反，只能分开核对。

检查 11：依赖锁的 Windows-only 条目必须带平台 marker
  python-ai/requirements.txt 由 Windows 开发机上的 pip-compile 生成（命令里没有
  --python-platform），Windows 分支上的传递依赖会以无 marker 的形式进锁。pywin32 在
  PyPI 上只有 win32 wheel ⇒ `docker build -f deploy/Dockerfile.python` 在 linux/amd64
  上死于 "from versions: none"，而宿主是 Windows 时这条完全不可见。

检查 12：前端时间显示只有一个入口
  页面的服务端时间一律走 hfusionhub-frontend/src/utils/date.ts，不得再出现
  replace('T',' ')（截字面量、丢偏移）或 getTimezoneOffset()（把某个国家的时区编进代码）。
  第九十五批前同一份数据在三种互相矛盾的解析theory并存，合起来必然在不同页面显示成不同时刻。

检查 13：写侧时钟三源同源，且判定列不读会话钟
  JVM `-Duser.timezone`、MySQL `--default-time-zone`、JDBC `serverTimezone` 在 dev/prod compose
  与 helm（values + 模板引用）上必须都声明、且归一化后同为 UTC；模板引用了 values 键才算数，
  只写键没人读=死配置。判定列（expires_at / recycle_expires_at / circuit_open_until）的比较式
  里不得出现 NOW()——NOW() 取会话时区的墙钟，列里存的是另一套，同一行的过期判定会随连接翻转。

检查 14：workflow 的 run 必须是块标量，续行才会到达 shell
  `run: cmd \\` + 缩进续行是 YAML 的 plain 多行标量：折行时换行被折叠成空格，shell 收到
  `\\ `（转义空格）而非续行，选项串带前导空格进不去。带续行的命令必须写 `run: |`。
  同时核对 ci.yml 仍调用四个离线冻结套件（通用 + 招投标三竖门）且用例文件在位——门禁消失
  比门禁变红更安静，第九十七批的三个竖门就是这样"绿了 47 天其实一次没跑"。

检查 15：python 侧的钟面并入同一 UTC 口径
  `datetime.now()`/`utcnow()`/`today()` 的零参写法、`time.localtime()`、少了 tz 的
  `fromtimestamp()` 读的是**进程时区**墙钟，容器里就是宿主/节点时区；app/ 下不得出现
  （ast 解析，注释与 docstring 里的说明文字不算违规）。同时 dev/prod compose 里每个
  python 工作负载、helm 的 python.yaml 与 plugin-runner.yaml 都必须声明 TZ=UTC，且模板
  真的引用 values 里的 tz 键——与检查 13 是同一件事的两半：13 钉 java 写侧三张钟面，
  这里钉 python 的钟面，两侧都钉死才有"同一瞬间一个墙钟"。

检查 16：审计库共享 SQLite 连接的取用与关闭都在 `_db_lock` 内
  `app/core/plugin/audit.py` 那个 `check_same_thread=False` 的连接被后台 flush 线程和
  请求线程共用。`db = _get_db()` 写在 `with _db_lock:` **之前**时，锁只排开"execute 撞
  execute"，排不开"锁外取到的连接对象 vs `_reset_db()` 的 close()"——被关掉的原生句柄
  再 execute 是解释器级 access violation，Python 异常接不住（第一百零三、一百零四批各
  踩到一次，退出码 139）。所以按形判：`_get_db()` 调用、以及除 `_get_db` 本体以外对
  `_db_conn` 的读写，都必须落在 `with _db_lock:` 的体内。适用面按"有没有碰这三个名字"
  算，一个都没扫到就判红——只认锁名的话，整组改名会让这条门静默变成空扫描。

检查 17：Flyway 在 CI 里必须传插件真读的旗标，且插件与运行时同源
  workflow 里的 `mvn flyway:migrate` 只认 `-Dflyway.url/user/password`，把连接信息写进
  `SPRING_DATASOURCE_*` 环境变量等于没传（第一百零八批：那个步骤从诞生起就红）。同时
  pom 必须把 flyway-maven-plugin 钉到 `${flyway.version}`——不声明时 Maven 按前缀浮动解析
  中央仓库最新版，与运行时 flyway-core 各自漂移。适用面按"调用次数=预期表"算，对不上就红。

检查 18：容器轨上"配置写了、实体或语义对不上"的四类断链
  ① compose 的 command 里 `python -m arq <模块>.WorkerSettings` 的模块必须真在该服务
  Dockerfile 的 COPY 集合里——第一百零九批实测：Dockerfile.python 只 COPY app/，worker 在
  容器里 ModuleNotFoundError 崩溃循环，队列侧 job 滞留而 API 层全程正常。
  ② 拓扑里的 redis 以 `--requirepass` 启动时，每个声明 `SPRING_DATA_REDIS_HOST` 的 java
  工作负载必须成对声明密码键——dev compose 缺这一对时登录 500
  RedisConnectionFailureException，而 prod compose 一直是成对的。
  ③ java 侧读来当 python 基址的属性（`@Value("${...:http://host:9000}")`）必须在
  application.yml 里写成 `${同一个环境变量:...}`，且那个变量在三档拓扑的 java 工作负载上都
  得声明——python-ai.base-url / python-ai.engine.url 曾是裸字面量，容器里 java 把解析请求
  打到自己的 localhost:9000（400 I/O error）。
  ④ 跑 arq worker 的服务不得继承（或自定义）打 HTTP 端口的存活探针——它不监听 9000，实测
  永久 unhealthy（probe_http=000），真正的崩溃循环反而被这片假红盖住。
  四条的适用面都按数量核对（表面缩小或整族消失=前提变了，判红）；helm 的 redis 不起 requirepass 故不在②。

用法:
  python scripts/static-checks.py --tenant-columns
  python scripts/static-checks.py --internal-token-keys
  python scripts/static-checks.py --test-counts
  python scripts/static-checks.py --flyway-doc-sync
  python scripts/static-checks.py --h2-schema-drift
  python scripts/static-checks.py --readme-claims
  python scripts/static-checks.py --helm-value-roots
  python scripts/static-checks.py --container-uid
  python scripts/static-checks.py --document-storage-root
  python scripts/static-checks.py --eval-harness-storage
  python scripts/static-checks.py --requirements-markers
  python scripts/static-checks.py --frontend-time-entry
  python scripts/static-checks.py --write-clock-caliber
  python scripts/static-checks.py --python-clock-caliber
  python scripts/static-checks.py --db-lock-lifetime
  python scripts/static-checks.py            # 全部检查
退出码: 0=通过, 1=发现违规
"""

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIGRATION_DIR = REPO / "java-backend" / "src" / "main" / "resources" / "db" / "migration"
CONFIG_FILE = REPO / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub" / "config" / "MybatisPlusConfig.java"
CONTROLLER_DIR = REPO / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub" / "controller"
JAVA_TEST_DIR = REPO / "java-backend" / "src" / "test"
PYTHON_TEST_DIR = REPO / "python-ai" / "tests"
FRONTEND_SRC_DIR = REPO / "hfusionhub-frontend" / "src"
FRONTEND_E2E_DIR = REPO / "hfusionhub-frontend" / "e2e"
README_FILE = REPO / "README.md"
AGENTS_FILE = REPO / "AGENTS.md"
CLAUDE_FILE = REPO / "CLAUDE.md"

problems: list[str] = []


# ── 检查 1：租户列完整性 ────────────────────────────────────────────────

def parse_tenant_ignore_tables() -> set[str]:
    """从 MybatisPlusConfig.java 提取 TENANT_IGNORE_TABLES 常量。"""
    text = CONFIG_FILE.read_text(encoding="utf-8")
    m = re.search(r"TENANT_IGNORE_TABLES\s*=\s*Set\.of\((.*?)\);", text, re.S)
    if not m:
        problems.append("MybatisPlusConfig.java: 未找到 TENANT_IGNORE_TABLES 定义")
        return set()
    body = m.group(1)
    return set(re.findall(r'"([^"]+)"', body))


def collect_tables_with_tenant() -> set[str]:
    """解析所有迁移 SQL，收集含 tenant_id 列的表名。"""
    with_tenant: set[str] = set()
    all_tables: set[str] = set()
    for sql_file in sorted(MIGRATION_DIR.glob("V*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        # CREATE TABLE xxx (...tenant_id...)
        for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*?)\)\s*(?:ENGINE|COMMENT|;|$)",
            text, re.S | re.I,
        ):
            table = m.group(1).lower()
            cols = m.group(2).lower()
            all_tables.add(table)
            if re.search(r"\btenant_id\b", cols):
                with_tenant.add(table)
        # ALTER TABLE xxx ADD COLUMN tenant_id ...
        for m in re.finditer(
            r"ALTER\s+TABLE\s+`?(\w+)`?\s+(?:ADD\s+(?:COLUMN\s+)?`?tenant_id`?|ADD\s+COLUMN\s+`?tenant_id`?)",
            text, re.S | re.I,
        ):
            with_tenant.add(m.group(1).lower())
    return with_tenant, all_tables


def check_tenant_columns() -> None:
    ignore = {t.lower() for t in parse_tenant_ignore_tables()}
    with_tenant, _ = collect_tables_with_tenant()
    # 迁移目录可能不包含所有表（H2 测试 schema 等），无法静态断言"全表"。
    # 这里校验：迁移中出现的表，若不在忽略表且无 tenant_id → 违规。
    # 迁移中未出现的表由数据库动态检查（smoke-test 覆盖）。
    migrated = set()
    for sql_file in MIGRATION_DIR.glob("V*.sql"):
        text = sql_file.read_text(encoding="utf-8")
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", text, re.I):
            migrated.add(m.group(1).lower())
    for table in sorted(migrated):
        if table in ignore:
            continue
        if table not in with_tenant:
            problems.append(
                f"表 '{table}' 不在 TENANT_IGNORE_TABLES 中且没有任何迁移为其添加 tenant_id 列"
                "（租户拦截器会注入 tenant_id 条件 → SQL 报错）"
            )
    if not problems:
        print(f"[ok] 租户列完整性：{len(migrated)} 张迁移表，全部有 tenant_id 或被显式忽略")


# ── 检查 2：内部 token 键一致性 ─────────────────────────────────────────

def check_internal_token_keys() -> None:
    bad: list[str] = []
    for java_file in CONTROLLER_DIR.glob("*.java"):
        text = java_file.read_text(encoding="utf-8")
        for m in re.finditer(r'@Value\("\$\{([^}]*internal-token[^}]*)\}"\)', text, re.I):
            key = m.group(1)
            base = key.split(":")[0].strip()
            if base not in ("python-ai.internal-token", "app.internal-token"):
                bad.append(f"{java_file.name}: @Value(\"${{{key}}}\")")
    if bad:
        problems.append("内部 token 键非标准（应为 python-ai.internal-token）:\n    " + "\n    ".join(bad))
    else:
        print("[ok] 内部 token 键一致性：所有 internal-token 使用标准键")

    check_internal_header_names()


# Java↔Python 内部契约锚点：头名/回调路径字符串必须两侧同时存在。
# 上一段的键名检查只覆盖 Java @Value 的配置键；头名字符串散落在
# AiClient / CallbackSignatureFilter 与 Python 的 internal_auth /
# vectorization 回调里——任一侧改名属于破坏性契约变更，CI 必须拦住。
CONTRACT_ANCHORS = [
    (
        REPO / "java-backend" / "src/main/java/com/hfusionhub/client/AiClient.java",
        ["X-Internal-Token"],
        "Java→Python 调用头",
    ),
    (
        REPO / "java-backend" / "src/main/java/com/hfusionhub/tenant/CallbackSignatureFilter.java",
        ["X-Callback-Signature", "X-Callback-Secret"],
        "Python→Java 回调验签头",
    ),
    (
        REPO / "python-ai" / "app/api/internal_auth.py",
        ["X-Internal-Token"],
        "Python 侧内部鉴权头",
    ),
    (
        REPO / "python-ai" / "app/api/vectorization.py",
        ["X-Callback-Secret", "X-Callback-Signature", "/api/documents/{document_id}/chunks"],
        "Python→Java 回调签名头与回调目标路径",
    ),
    (
        REPO / "java-backend" / "src/main/java/com/hfusionhub/service/impl/VectorizationServiceImpl.java",
        ["/api/documents/", "/chunks"],
        "Java 侧调用的 Python 删除端点路径",
    ),
]


def check_internal_header_names() -> None:
    bad: list[str] = []
    for path, needles, desc in CONTRACT_ANCHORS:
        if not path.exists():
            bad.append(f"{path}: 文件不存在（契约锚点被移动？请同步更新 static-checks.py）")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in text:
                bad.append(f"{path.name}: 未找到契约字符串 '{needle}'（{desc}）")
    if bad:
        problems.append("Java↔Python 内部契约锚点缺失:\n    " + "\n    ".join(bad))
    else:
        print(f"[ok] 内部契约锚点：{len(CONTRACT_ANCHORS)} 处头名/路径两侧一致")


# ── 检查 3：测试计数文档同步 ────────────────────────────────────────────

def count_java_tests() -> int:
    return sum(
        1
        for f in JAVA_TEST_DIR.rglob("*.java")
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines()
        if re.match(r"\s*@(Test|ParameterizedTest|RepeatedTest)\b", line)
    )


def count_python_tests() -> int:
    return sum(
        len(re.findall(r"(?m)^\s*(?:async\s+)?def\s+test_\w+", f.read_text(encoding="utf-8", errors="replace")))
        for f in PYTHON_TEST_DIR.rglob("*.py")
    )


def count_frontend_unit_tests() -> int:
    return sum(
        len(re.findall(r"(?m)^\s*\b(?:it|test)\s*\(", f.read_text(encoding="utf-8", errors="replace")))
        for f in FRONTEND_SRC_DIR.rglob("*.spec.ts")
    )


def count_frontend_e2e_tests() -> int:
    return sum(
        len(re.findall(r"(?m)^\s*\btest\s*\(", f.read_text(encoding="utf-8", errors="replace")))
        for f in FRONTEND_E2E_DIR.rglob("*.spec.ts")
    )


def extract_doc_counts(text: str, source: str) -> dict[str, int] | None:
    """从 README 徽章、AGENTS.md Tests 行或 CLAUDE.md 测试表提取声称的计数；格式变化时返回 None。"""
    m = re.search(
        r"Tests-Python%20(\d+)%20%7C%20Java%20(\d+)%20%7C%20Frontend%20(\d+)-success", text
    )
    if m:
        return {"python": int(m.group(1)), "java": int(m.group(2)), "frontend": int(m.group(3))}
    m = re.search(r"\*\*Tests\*\*:\s*Java\s*(\d+)\s*·\s*Python\s*(\d+)\s*·\s*Frontend\s*(\d+)", text)
    if m:
        return {"java": int(m.group(1)), "python": int(m.group(2)), "frontend": int(m.group(3))}
    # CLAUDE.md 测试表：三行 markdown 表格
    m_py = re.search(r"\|\s*python-ai\s*\|[^|]*\|\s*(\d+)\s*\|", text)
    m_ja = re.search(r"\|\s*java-backend\s*\|[^|]*\|\s*(\d+)\s*\|", text)
    m_fe = re.search(r"\|\s*frontend\s*\|[^|]*\|\s*(\d+)\s*unit", text)
    if m_py and m_ja and m_fe:
        return {"python": int(m_py.group(1)), "java": int(m_ja.group(1)), "frontend": int(m_fe.group(1))}
    problems.append(f"{source}: 未找到测试计数标记（README 徽章 / AGENTS.md '**Tests**:' 行 / CLAUDE.md 测试表格式已变化，请更新检查 3 的正则）")
    return None


def check_test_counts() -> None:
    actual = {
        "java": count_java_tests(),
        "python": count_python_tests(),
        "frontend": count_frontend_unit_tests(),
    }
    e2e = count_frontend_e2e_tests()
    for source_file, pattern in ((README_FILE, "badge"), (AGENTS_FILE, "Tests line"), (CLAUDE_FILE, "test table")):
        if not source_file.exists():
            # AGENTS.md / CLAUDE.md 已随"去 AI 协作痕迹"清理移除；README 为唯一计数权威
            if source_file == README_FILE:
                problems.append(f"{source_file.name}: 文件不存在，无法校验测试计数")
            continue
        claimed = extract_doc_counts(source_file.read_text(encoding="utf-8"), source_file.name)
        if claimed is None:
            continue
        diffs = [f"{k}: 文档 {claimed[k]} ≠ 实测 {actual[k]}" for k in actual if claimed[k] != actual[k]]
        if diffs:
            problems.append(f"{source_file.name} 测试计数漂移（{pattern}）:\n    " + "\n    ".join(diffs))
        else:
            print(
                f"[ok] 测试计数同步（{source_file.name}）："
                f"Java {actual['java']} · Python {actual['python']} · 前端单测 {actual['frontend']}（另有 {e2e} 个 E2E 未计入徽章）"
            )


# ── 检查 4：Flyway 版本窗口文档同步 ─────────────────────────────────────

FLYWAY_DOC_FILES = (
    CLAUDE_FILE,
    AGENTS_FILE,
    README_FILE,
    REPO / "docs" / "java-backend.md",
    REPO / "docs" / "database.md",
)


def latest_migration_version() -> int:
    latest = 0
    for f in MIGRATION_DIR.glob("V*.sql"):
        m = re.match(r"V(\d+)__", f.name)
        if m:
            latest = max(latest, int(m.group(1)))
    return latest


def check_flyway_doc_sync() -> None:
    latest = latest_migration_version()
    if latest == 0:
        problems.append("未找到任何 Flyway 迁移脚本（V<n>__*.sql）")
        return
    bad: list[str] = []
    for f in FLYWAY_DOC_FILES:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"V1[–-]V(\d+)", text):
            claimed = int(m.group(1))
            if claimed != latest:
                bad.append(f"{f.name}: 迁移区间写作 V1–V{claimed}，实际最新版本为 V{latest}")
        for m in re.finditer(r"\bV(\d+)\+", text):
            claimed = int(m.group(1))
            if claimed != latest + 1:
                bad.append(f"{f.name}: 新脚本版本窗口写作 V{claimed}+，应为 V{latest + 1}+")
    if bad:
        problems.append("Flyway 版本窗口文档漂移:\n    " + "\n    ".join(bad))
    else:
        print(f"[ok] Flyway 版本窗口同步：最新迁移 V{latest}，新脚本窗口 V{latest + 1}+")


# 当前态文档声称对账（2026-09-22 架构减法批次）：
# 这些词描述的能力已被移除或从未实现，不允许再出现在"描述现状"的文档里。
# 历史记录类文档（CHANGELOG / ROADMAP / TODO / OPTIMIZATION_PLAN /
# CLEANUP_BACKLOG / GRAPHRAG_REVIEW / adr/）不参与扫描——它们记录过去。
BANNED_CLAIMS = {
    "PreToolUse": "工具门禁的实际实现是 ToolRegistry 七段门禁链，不存在 PreToolUse 钩子",
    "Bash 子命令": "仓库无 Bash 工具，子命令粒度校验从未实现",
    "Electron": "无 Electron 客户端代码",
    "Telegram": "IM 渠道实际只有飞书/钉钉/企业微信",
    "Discord": "IM 渠道实际只有飞书/钉钉/企业微信",
    "WhatsApp": "IM 渠道实际只有飞书/钉钉/企业微信",
    "七种 IM": "IM 渠道实际只有飞书/钉钉/企业微信三种",
    "图谱": "图谱召回通道已按 GRAPHRAG_REVIEW 复评移除（向量+BM25+RRF）",
}
CLAIM_SCAN_FILES = [
    "README.md",
    "README_EN.md",
    "docs/python-ai.md",
    "docs/ARCHITECTURE.md",
    "docs/PROJECT_TOUR.md",
    "docs/ACCESS_MAP.md",
]


def check_readme_claims() -> None:
    """当前态文档不得声称已移除/未实现的能力（声称-实现对账防复发）。"""
    bad: list[str] = []
    for name in CLAIM_SCAN_FILES:
        f = REPO / name
        if not f.exists():
            continue
        for lineno, line in enumerate(
                f.read_text(encoding="utf-8").splitlines(), 1):
            for word, reason in BANNED_CLAIMS.items():
                if word in line:
                    bad.append(f"{name}:{lineno} 出现「{word}」（{reason}）")
    if bad:
        problems.append("文档声称与实现不一致:\n    " + "\n    ".join(bad))
    else:
        print(f"[ok] 文档声称对账：{len(CLAIM_SCAN_FILES)} 个当前态文档无禁用声称")


def check_h2_schema_drift() -> None:
    """H2 测试 schema 与 Flyway 迁移链的漂移防护（R15-22 收尾）。

    逻辑在 scripts/check-h2-schema-drift.py（基线模式：只拦"新增"漂移）。
    """
    script = REPO / "scripts" / "check-h2-schema-drift.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        problems.append(f"H2 schema 出现基线之外的新增漂移:\n    {output}")
    else:
        for line in output.splitlines():
            cleaned = re.sub(r"^\[(?:ok|info)\]\s*", "", line)
            if cleaned:
                print(f"[ok] {cleaned}")


# ── 检查 7：Helm chart 引用的 .Values 根必须存在 ────────────────────────

HELM_CHART = REPO / "deploy" / "helm" / "hfusionhub"


def check_helm_value_roots() -> None:
    """模板里用到的 `.Values.<root>` 必须在 values.yaml 顶层有定义。

    Go 模板对不存在的根取字段是**执行期报错**，不是静默走 default：
    `{{ .Values.python.taskQueueMode | default "inline" }}` 在 `python` 根缺失时直接
    抛 `nil pointer evaluating interface {}.taskQueueMode`，整张 chart 渲染失败——
    即 `helm install` 根本装不起来。helm 二进制在 CI 与多数开发机上都没有，
    故这里用纯文本核对同一件事，让这类笔误在评审阶段就红。
    """
    if not HELM_CHART.is_dir():
        problems.append(f"helm chart 目录缺失：{HELM_CHART}")
        return
    values_text = (HELM_CHART / "values.yaml").read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Za-z_][\w-]*):", values_text, re.MULTILINE))
    bad: list[str] = []
    checked = 0
    for tpl in sorted((HELM_CHART / "templates").glob("*.yaml")):
        checked += 1
        for lineno, line in enumerate(tpl.read_text(encoding="utf-8").splitlines(), 1):
            for root in re.findall(r"\.Values\.([A-Za-z_][\w-]*)", line):
                if root not in declared:
                    bad.append(
                        f"templates/{tpl.name}:{lineno} 引用 .Values.{root}，"
                        f"但 values.yaml 顶层没有该键（可用根：{sorted(declared)}）"
                    )
    if bad:
        problems.append("Helm 模板引用了未定义的 values 根:\n    " + "\n    ".join(bad))
    else:
        print(f"[ok] Helm values 根一致性：{checked} 个模板引用的根全部在 values.yaml 定义")


# ── 检查 8：容器运行身份三处同源 ────────────────────────────────────────

DOCKERFILE_PYTHON = REPO / "deploy" / "Dockerfile.python"
DOCKERFILE_JAVA = REPO / "deploy" / "Dockerfile.java"
HELM_VALUES = HELM_CHART / "values.yaml"


def _pinned_ids(text: str) -> tuple[list[str], list[str]]:
    """返回镜像声明的 (uid 候选, gid 候选)；没写 -u/-g 就是空列表。

    注释行要跳过：说明性文字里出现 `useradd -r` 不算一次声明。
    """
    joined = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    uid = re.findall(r"\b(?:useradd|adduser)\b[^\n&]*? -u\s+(\d+)", joined)
    gid = re.findall(r"\b(?:groupadd|addgroup)\b[^\n&]*? -g\s+(\d+)", joined)
    return uid, gid


def _pod_security_from_values(text: str) -> dict[str, int]:
    """取 values.yaml 里 podSecurity 段的三个号。"""
    block = re.search(r"^podSecurity:\n((?:[ \t]+\S.*\n)+)", text, re.MULTILINE)
    if block is None:
        return {}
    return {
        key: int(value)
        for key, value in re.findall(
            r"^\s+(runAsUser|runAsGroup|fsGroup):\s*(\d+)\s*$", block.group(1), re.MULTILINE
        )
    }


def check_container_uid_consistency() -> None:
    """java/python 镜像钉的 uid/gid 与 helm podSecurity 声明的必须是同一组号。

    卷可写与否取决于"进程身份"与"卷属主"是否对齐。`useradd -r` / `adduser -S` 把身份
    交给基镜像当时占了哪些号（系统池 100–999，重建即漂移），而 helm 的 fsGroup 是另一个
    手写的数字——两处各写一遍、无人核对，正是第八十三批"模板读了一个不存在的键"的兄弟形态。
    纯文本核对，CI 不需要 docker 或 helm。
    """
    images = (
        ("deploy/Dockerfile.python", DOCKERFILE_PYTHON),
        ("deploy/Dockerfile.java", DOCKERFILE_JAVA),
    )
    bad: list[str] = []
    for label, path in images:
        if not path.is_file():
            bad.append(f"{label} 缺失")
            continue
        uid, gid = _pinned_ids(path.read_text(encoding="utf-8"))
        if len(uid) != 1:
            bad.append(
                f"{label} 未用 -u 钉死 uid（找到 {len(uid)} 处；`-r`/`-S` 的号由基镜像决定）"
            )
        if len(gid) != 1:
            bad.append(f"{label} 未用 -g 钉死 gid（找到 {len(gid)} 处）")
        if len(uid) == 1 and len(gid) == 1 and uid[0] != gid[0]:
            bad.append(f"{label} uid={uid[0]} 与 gid={gid[0]} 不同号，三处书写无法对齐")

    if not HELM_VALUES.is_file():
        bad.append(f"values.yaml 缺失：{HELM_VALUES}")
    else:
        values = _pod_security_from_values(HELM_VALUES.read_text(encoding="utf-8"))
        for key in ("runAsUser", "runAsGroup", "fsGroup"):
            if key not in values:
                bad.append(f"values.yaml 的 podSecurity 缺 {key}（helm 侧未声明运行身份）")
        if values:
            for label, path in images:
                if not path.is_file():
                    continue
                uid, gid = _pinned_ids(path.read_text(encoding="utf-8"))
                if len(uid) != 1 or len(gid) != 1:
                    continue
                if int(uid[0]) != values.get("runAsUser") or int(gid[0]) != values.get("runAsGroup"):
                    bad.append(
                        f"{label} 钉的是 uid={uid[0]}/gid={gid[0]}，与 helm podSecurity"
                        f"（runAsUser={values.get('runAsUser')}, "
                        f"runAsGroup={values.get('runAsGroup')}, "
                        f"fsGroup={values.get('fsGroup')}）不一致"
                    )
            if len(set(values.values())) > 1:
                bad.append(
                    f"values.yaml podSecurity 三个号不相同：{values}"
                    "（runAsGroup 与 fsGroup 同号，java/python 才能在共用卷上互写）"
                )

    if bad:
        problems.append("容器运行身份不一致:\n    " + "\n    ".join(bad))
    else:
        uid, _ = _pinned_ids(DOCKERFILE_PYTHON.read_text(encoding="utf-8"))
        print(f"[ok] 容器运行身份同源：java/python 镜像与 helm podSecurity 均钉 uid={uid[0]}")


# ── 检查 9：Java↔Python 文档目录的路径契约 ──────────────────────────────

COMPOSE_DEV = REPO / "docker" / "docker-compose.yml"
COMPOSE_PROD = REPO / "deploy" / "docker-compose.prod.yml"
HELM_PYTHON_TEMPLATE = HELM_CHART / "templates" / "python.yaml"
JAVA_DOCUMENT_SERVICE = (
    REPO / "java-backend" / "src" / "main" / "java" / "com" / "hfusionhub"
    / "service" / "impl" / "DocumentServiceImpl.java"
)


def _strip_comments(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def _compose_service_blocks(text: str) -> dict[str, str]:
    """compose 的 `services:` 段按两空格缩进切成 {服务名: 块文本}。"""
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    inside = False
    for line in text.splitlines():
        if not inside:
            inside = line.rstrip() == "services:"
            continue
        if line and not line.startswith((" ", "\t", "#")):
            break
        named = re.match(r"^  ([A-Za-z0-9_.-]+):\s*(#.*)?$", line)
        if named:
            if current is not None:
                blocks[current] = "\n".join(buf)
            current, buf = named.group(1), []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


def _declared_env(block: str, key: str) -> str | None:
    """工作负载声明的环境变量，兼容 compose 的 `KEY: value` 与 k8s 的 name/value 两种写法。"""
    block = _strip_comments(block)
    flat = re.search(rf"^\s*{re.escape(key)}:\s*\"?([^\n\"]+)\"?\s*$", block, re.MULTILINE)
    if flat:
        return flat.group(1).strip()
    nested = re.search(
        rf'- name: {re.escape(key)}\n\s+value:\s*"?([^\n"]+)"?\s*$', block, re.MULTILINE
    )
    return nested.group(1).strip() if nested else None


def _declared_document_root(block: str) -> str | None:
    """python 工作负载声明的 DOCUMENT_STORAGE_ROOT，兼容 compose 与 k8s 两种写法。"""
    return _declared_env(block, "DOCUMENT_STORAGE_ROOT")


def _mount_targets(block: str) -> list[str]:
    """块内出现的所有挂载目标（compose 的 `src:dst[:ro]` 与 k8s 的 mountPath）。"""
    text = _strip_comments(block)
    targets = re.findall(r"^\s*-\s+\S+:(/\S+?)(?::\S+)?\s*$", text, re.MULTILINE)
    targets += re.findall(r"^\s*mountPath:\s*(/\S+)\s*$", text, re.MULTILINE)
    return [t.rstrip("/") for t in targets]


def _covers(targets: list[str], path: str) -> bool:
    return any(path == t or path.startswith(t + "/") for t in targets)


def _java_document_root() -> tuple[str | None, list[str]]:
    """java 运行容器里的文档目录 = 末段 WORKDIR + DocumentServiceImpl 的 UPLOAD_DIR。

    派生而不是硬编码：这两个锚点一变，三处部署面的 root 就同时失效，必须让门禁先响。
    """
    if not DOCKERFILE_JAVA.is_file():
        return None, [f"deploy/Dockerfile.java 缺失：{DOCKERFILE_JAVA}"]
    stages = re.split(
        r"^FROM\b", DOCKERFILE_JAVA.read_text(encoding="utf-8"), flags=re.MULTILINE
    )[1:]
    workdirs = re.findall(r"^WORKDIR\s+(/\S+)\s*$", stages[-1] if stages else "", re.MULTILINE)
    if len(workdirs) != 1:
        return None, [
            f"Dockerfile.java 运行阶段的 WORKDIR 不唯一或缺失，无法派生 java 的文档目录：{workdirs}"
        ]
    if not JAVA_DOCUMENT_SERVICE.is_file():
        return None, [f"DocumentServiceImpl.java 缺失：{JAVA_DOCUMENT_SERVICE}"]
    upload_dir = re.search(
        r'static\s+final\s+String\s+UPLOAD_DIR\s*=\s*"([^"]+)"',
        JAVA_DOCUMENT_SERVICE.read_text(encoding="utf-8"),
        re.IGNORECASE,
    )
    if upload_dir is None:
        return None, [
            "DocumentServiceImpl.java 里找不到 UPLOAD_DIR 常量（java 侧的上传锚点变了，本检查需同步）"
        ]
    return f"{workdirs[0].rstrip('/')}/{upload_dir.group(1).strip('/')}", []


def check_document_storage_root_contract() -> None:
    """每个部署面上，python 工作负载必须与 java 用**同一个绝对路径**看见文档文件。

    java 入库的 `document.file_path` 是它自己容器内的绝对路径，`/api/parse` 收到后要求该
    路径在 python 容器里真实存在且落在 `DOCUMENT_STORAGE_ROOT` 之下（validators.py 的
    `resolve(strict=True)` + `relative_to`）；`/api/ingest/url` 的反向回传同样按路径落地。
    于是"挂 uploads 卷"与"设 root"必须**成对**出现在同一个 python 工作负载上。dev compose
    的 fullstack 档两处都缺过（`DOCUMENT_STORAGE_ROOT` 的镜像默认值是宿主开发态相对路径），
    结果是容器化启动下每个文档解析都 400 code 10001——纯文本核对，CI 不需要 docker。
    """
    root, anchor_bad = _java_document_root()
    bad = list(anchor_bad)
    if root is None:
        problems.append("文档目录路径契约无法核对:\n    " + "\n    ".join(bad))
        return

    workloads: list[tuple[str, str]] = []
    for label, path in (
        ("docker/docker-compose.yml", COMPOSE_DEV),
        ("deploy/docker-compose.prod.yml", COMPOSE_PROD),
    ):
        if not path.is_file():
            bad.append(f"{label} 缺失")
            continue
        for name, block in _compose_service_blocks(path.read_text(encoding="utf-8")).items():
            if name.startswith("python"):
                workloads.append((f"{label} 的服务 {name}", block))
    if HELM_PYTHON_TEMPLATE.is_file():
        workloads.append(
            ("helm templates/python.yaml", HELM_PYTHON_TEMPLATE.read_text(encoding="utf-8"))
        )
    else:
        bad.append(f"helm 的 python 模板缺失：{HELM_PYTHON_TEMPLATE}")

    for label, block in workloads:
        declared = _declared_document_root(block)
        targets = _mount_targets(block)
        if declared is None:
            bad.append(
                f"{label} 没有 DOCUMENT_STORAGE_ROOT：python 会退回镜像默认值 "
                f"../java-backend/uploads/documents（宿主开发态路径），java 传来的 "
                f"{root}/… 在它容器里不存在，解析一律 400"
            )
        elif declared != root:
            bad.append(
                f"{label} 的 DOCUMENT_STORAGE_ROOT={declared} 与 java 容器的文档目录 {root} "
                f"不同号：同一份文件两边互相看不见，/api/parse 只会回 400"
            )
        if declared is not None and not _covers(targets, root):
            bad.append(
                f"{label} 声明了 root={declared}，却没有任何卷挂在 {root} 或它的祖先路径上："
                f"读不到 java 写的文件，python 自己写的摄取暂存也会随容器重建消失"
            )
        elif declared is None and not _covers(targets, root):
            bad.append(f"{label} 既没有 DOCUMENT_STORAGE_ROOT，也没有挂载覆盖 {root}")

    if bad:
        problems.append("文档目录路径契约不成立:\n    " + "\n    ".join(bad))
    else:
        print(f"[ok] 文档目录路径契约：{len(workloads)} 个 python 工作负载与 java 同用 {root}")


# ── 检查 10：评测产物落点在卷上、且与共享根分面 ──────────────────────────

HELM_PYTHON_CONTAINER = "- name: python-ai"


def _helm_rwx_mounts(text: str) -> set[str]:
    """返回挂在 ReadWriteMany PVC 上的 mountPath（把 卷名→PVC 名→访问模式 串起来）。

    名称一律取整行余量而不是 `\\S+`：模板里的 PVC 名是 `{{ .Release.Name }}-xxx`，
    含空格，用 `\\S+` 会把每个名字都读成 `{{`，于是所有 PVC 塌成一个键、
    访问模式互相顶包——RWO 也会被当成 RWX 放过。
    """
    modes_by_claim: dict[str, list[str]] = {}
    for m in re.finditer(
        r"kind: PersistentVolumeClaim\n(?:.*\n)*?^  accessModes:\n((?:\s+-\s+\S+\n)+)",
        text,
        re.MULTILINE,
    ):
        name = re.search(r"^  name:\s*(.+?)\s*$", text[m.start():m.end()], re.MULTILINE)
        if name:
            modes_by_claim[name.group(1)] = re.findall(r"^\s+-\s+(\S+)", m.group(1), re.MULTILINE)
    modes_by_volume = dict(
        re.findall(
            r"- name:\s*(.+?)\s*\n\s+persistentVolumeClaim:\s*\n\s+claimName:\s*(.+?)\s*$",
            text,
            re.MULTILINE,
        )
    )
    out: set[str] = set()
    for volume, mount in re.findall(
        r"- name:\s*(.+?)\s*\n\s+mountPath:\s*(.+?)\s*$", text, re.MULTILINE
    ):
        claim = modes_by_volume.get(volume)
        if claim and "ReadWriteMany" in modes_by_claim.get(claim, []):
            out.add(mount.rstrip("/"))
    return out


def check_eval_harness_storage() -> None:
    """评测产物（runs/reports/scores）与 judge 缓存的落点必须在卷上，且两者分面。

    三个落点此前是模块级硬编码的相对目录，容器里解析成 /app/data —— 三档 shipped 拓扑
    没有任何一档把卷挂在那里（compose 只挂 /data，helm 连 /data 都不存在）。后果不是少了
    一个优化：`/score`、`/slides`、`/report`、`/diff` 是按"文件还在"读回的，容器或 Pod
    一重建就全部 404，helm 两副本下 A 生成的报告对 B 根本不可见。
    落点也不能一把梭：产物是"写一次、之后按文件名读回"⇒ 该共享（helm 必须 RWX）；judge
    缓存是整文件 read-modify-write ⇒ 与共享根同目录时副本会互相覆盖，只能按 POD_NAME 分。
    """
    workloads: list[tuple[str, str, bool]] = []
    for label, path in (
        ("docker/docker-compose.yml", COMPOSE_DEV),
        ("deploy/docker-compose.prod.yml", COMPOSE_PROD),
    ):
        if not path.is_file():
            problems.append(f"评测产物落点无法核对：{label} 缺失")
            continue
        for name, block in _compose_service_blocks(path.read_text(encoding="utf-8")).items():
            if name.startswith("python"):
                workloads.append((f"{label} 的服务 {name}", block, False))
    if HELM_PYTHON_TEMPLATE.is_file():
        text = HELM_PYTHON_TEMPLATE.read_text(encoding="utf-8")
        # 模板里没有 python 容器时无从核对（本检查只管落点，不管副本数怎么来）
        if HELM_PYTHON_CONTAINER in text:
            workloads.append(("helm templates/python.yaml", text, True))

    bad: list[str] = []
    for label, block, is_helm in workloads:
        data_dir = _declared_env(block, "EVAL_HARNESS_DATA_DIR")
        cache = _declared_env(block, "EVAL_JUDGE_CACHE_PATH")
        targets = _mount_targets(block)
        if data_dir is None:
            bad.append(
                f"{label} 没有 EVAL_HARNESS_DATA_DIR：python 会退回镜像默认值 "
                f"data/eval_harness（相对 WORKDIR=/app ⇒ /app/data，不在任何卷上），"
                f"评测产物随容器重建消失"
            )
        elif not data_dir.startswith("/"):
            bad.append(f"{label} 的 EVAL_HARNESS_DATA_DIR={data_dir} 不是绝对路径（仍在镜像层）")
        elif not _covers(targets, data_dir):
            bad.append(
                f"{label} 的 EVAL_HARNESS_DATA_DIR={data_dir} 不在任何挂载点上："
                f"/score、/slides、/report、/diff 四个读端点按文件名读回，重建即 404"
            )
        elif is_helm and data_dir not in _helm_rwx_mounts(block):
            bad.append(
                f"{label} 的 {data_dir} 没有挂在 ReadWriteMany PVC 上：python 有 2 副本，"
                f"副本 A 生成的报告必须对副本 B 可见"
            )
        if cache is None:
            bad.append(
                f"{label} 没有 EVAL_JUDGE_CACHE_PATH：judge 缓存落回镜像层，"
                f"且与共享产物同根时会整文件互相覆盖"
            )
        elif data_dir and cache.startswith(data_dir.rstrip("/") + "/") and "$(POD_NAME)" not in cache:
            bad.append(
                f"{label} 的缓存 {cache} 落在共享根 {data_dir} 下却没有按 $(POD_NAME) 分目录："
                f"judge 缓存是整文件 read-modify-write，多进程/多副本共用一个文件会互相覆盖"
            )

    if bad:
        problems.append("评测产物落点不成立:\n    " + "\n    ".join(bad))
    else:
        print(f"[ok] 评测产物落点：{len(workloads)} 个 python 工作负载的产物在卷上、缓存已分面")


# ── 检查 11：锁里的 Windows-only 依赖必须带平台 marker ────────────────────

# 两份锁出自同一次单平台 pip-compile，所以同一个缺陷是两份一起坏：requirements.txt 是
# 镜像装的（deploy/Dockerfile.python:16），requirements-dev.txt 是 CI 的 python job 装的
# （ci.yml:155/178/215、plugin-security.yml:21、eval-nightly.yml:168，全部 ubuntu-latest）。
# 只核前者会让 CI 继续死在同一行上。
REQUIREMENTS_TXT = REPO / "python-ai" / "requirements.txt"
REQUIREMENTS_DEV_TXT = REPO / "python-ai" / "requirements-dev.txt"
LOCK_FILES = (REQUIREMENTS_TXT, REQUIREMENTS_DEV_TXT)

# 上游只在 Windows 上需要的包，及其进锁的原因（`# via` 那句）。
# pywin32 在 PyPI 上只有 win32 wheel、没有 sdist ⇒ linux/amd64 解析直接失败；
# win32-setctime 装得上但不该装。新增 Windows-only 传递依赖时必须同步这里，
# 否则门禁对新条目一无所知——锁是 pip-compile 在无 --python-platform 的宿主上生成的。
WINDOWS_ONLY_PINS = {
    "pywin32": "docker SDK",
    "win32-setctime": "loguru",
}

# 方向相反的同一条款：只在**非** Windows 上才需要的包。uvicorn 的 `standard` extra 把
# uvloop 钉在 `sys_platform != "win32"` 上，pip-compile 在 Windows 宿主上按 marker 为假
# 直接不写它 ⇒ 锁里既没有这条 pin 也没有它的哈希；Linux 侧 marker 为真，pip 只好拿 extra
# 自带的 `!=0.15.0,!=0.15.1,>=0.14.0` 去解析，而哈希模式不接受非 `==` 的传递依赖：
#   2582.1 ERROR: In --require-hashes mode, all requirements must have their versions
#                pinned with ==. These do not: uvloop!=0.15.0,!=0.15.1,>=0.14.0
# 所以这里核两件事：条目存在，且 marker 排除 win32（无 marker 会让生成锁的那台 Windows
# 宿主自己装不上）。新增非 Windows 专属传递依赖时同步这里，理由同上——锁是单平台编译的。
NON_WINDOWS_ONLY_PINS = {
    "uvloop": 'uvicorn[standard] extra（sys_platform != "win32"）',
}


def _lock_pins(text: str) -> list[tuple[str, str, int, int]]:
    """返回 (规范化包名, marker, 行号, 哈希条数)，marker 只看条目首行。

    条目形态：首行 `name[extras]==version [; marker] \\`，其后是 `--hash=` 续行和
    `# via` 段。marker 只从首行读——从续行找回 marker 会让"有 marker"与"没 marker"看起来一样。
    extras 参与匹配但不进包名：锁里 `uvicorn[standard]`、`jsonschema[format-nongpl]`、
    `cyclonedx-python-lib[validation]` 都是这种形态，早先的正则不含 `[` ⇒ 它们从计数里
    直接消失（prod 74/77、dev 97/102），一个手工追加的无哈希 `foo[bar]==1.2.3` 正好落在
    这个盲点上。
    """
    out: list[list] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("--hash=") and out:
            out[-1][3] += 1
            continue
        if not stripped or stripped.startswith("#") or stripped.startswith("--"):
            continue
        head = stripped.split(" \\")[0].strip()
        m = re.match(
            r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?==([^;\s]+)(?:\s*;\s*(.*))?$",
            head,
        )
        if m:
            out.append([m.group(1).lower().replace("_", "-"), m.group(3) or "", lineno, 0])
    return [(name, marker, lineno, counts) for name, marker, lineno, counts in out]


def check_requirements_platform_markers() -> None:
    """锁的可安装面：Windows-only 条目要带 marker，且哈希锁定不能只锁一半。两份锁都核。

    两条都来自第八十八批第一次真实 `docker build -f deploy/Dockerfile.python`：
    ① `pywin32==312` 没有 marker，pip 在 linux/amd64 上死于
      `Could not find a version that satisfies the requirement pywin32==312 (from versions: none)`
      —— PyPI 上它只有 win32 wheel、没有 sdist。宿主是 Windows 时解析得动，所以开发机不可见。
    ② 修完 ① 之后撞到 `Hashes are required in --require-hashes mode, but they are missing
      from some requirements`：`--require-hashes` 是 pip 在"任一条目带哈希"时**自动**开启的，
      而 `65b3ef8b` 手工往锁尾追加了三条没有哈希的 opentelemetry pin（`requirements.in` 里
      没有它们）。这条不限平台，CI 的 `pip install -r requirements.txt` 一起中招。
    ③ 修完 ② 之后同一次构建走到 collect 末尾（2582 秒）死于 uvloop——它是 `uvicorn[standard]`
      在非 Windows 上的依赖，单平台编译的锁里根本没有这一条（见 NON_WINDOWS_ONLY_PINS）。
      形状与 ① 同根、方向相反，代价是"锁修好了但镜像仍装不上"，且要让 extra 自带的 >= 规格
      解析到最后才报，所以反馈周期是一整次构建。
    docs/PRODUCTION_OPS.md §10.2 把"首次构建即是验收"写成了两个 Dockerfile 的验收方式，
    而 CI 的 docker-build 与 eval-nightly 恰好都断在这两行上，所以没有任何一处会报它。
    """
    missing = [lock for lock in LOCK_FILES if not lock.is_file()]
    if missing:
        problems.append("依赖锁缺失，无法核对可安装面: " + ", ".join(str(m) for m in missing))
        return

    ok_lines: list[str] = []
    for lock in LOCK_FILES:
        # 门禁测试会把 LOCK_FILES 换成 tmp_path 里的锁，那时 relative_to 会抛，退化成文件名即可
        rel = lock.relative_to(REPO).as_posix() if lock.is_relative_to(REPO) else lock.name
        pins = _lock_pins(lock.read_text(encoding="utf-8"))
        bad = [
            f"{rel}:{lineno} {name}==…（由 {WINDOWS_ONLY_PINS[name]} 引入）没有 marker："
            f"Linux 环境会连 Windows-only 依赖一起要，pywin32 这类 PyPI 上只有 win32 wheel 的直接"
            f"解析失败（docker build 死于 from versions: none），纯 Python 的那类则装进用不到的包"
            for name, marker, lineno, _ in pins
            if name in WINDOWS_ONLY_PINS and "win32" not in marker
        ]
        found = {name for name, _, _, _ in pins}
        bad += [
            f"{rel} 里根本没有 {name}（{NON_WINDOWS_ONLY_PINS[name]} 引入）："
            f"锁在 Windows 宿主上编译时按 marker 为假把它跳过了，Linux 侧 pip 只能拿 extra 自带的"
            f">= 规格去解析，而 --require-hashes 不接受非 == 的传递依赖（docker build 死于 "
            f"'all requirements must have their versions pinned with =='）"
            for name in sorted(NON_WINDOWS_ONLY_PINS)
            if name not in found
        ]
        bad += [
            f"{rel}:{lineno} {name}==… 的 marker 没有排除 win32（marker={marker or '无'}）："
            f"生成这份锁的 Windows 宿主与本地开发态会装不上它"
            for name, marker, lineno, _ in pins
            if name in NON_WINDOWS_ONLY_PINS and ("win32" not in marker or "!=" not in marker)
        ]
        hashed = [pin for pin in pins if pin[3]]
        if hashed and len(hashed) != len(pins):
            bad += [
                f"{rel}:{lineno} {name}==… 没有 --hash，而锁里另有 {len(hashed)} 条带哈希"
                f"⇒ pip 自动进入 --require-hashes 并拒绝这一条（任何平台的 pip install -r 都失败）"
                for name, _, lineno, counts in pins
                if not counts
            ]
        if bad:
            problems.append(f"依赖锁不是可安装的锁（{rel}）:\n    " + "\n    ".join(bad))
            continue
        windows_pins = sorted(n for n, _, _, _ in pins if n in WINDOWS_ONLY_PINS)
        non_windows_pins = sorted(n for n, _, _, _ in pins if n in NON_WINDOWS_ONLY_PINS)
        ok_lines.append(
            f"{rel}：{len(pins)} 条 pin（{len(hashed)} 条带哈希，形态一致），"
            f"Windows-only 已带 marker：{', '.join(windows_pins) or '无此类条目'}；"
            f"非 Windows 专属依赖已钉且排除 win32：{', '.join(non_windows_pins) or '无此类条目'}"
        )
    if ok_lines:
        print(f"[ok] 依赖锁可安装面：" + "；".join(ok_lines))


# ── 检查 12：前端时间显示只有一个入口 ──────────────────────────────────

FRONTEND_TIME_ROOTS = ("pages", "components", "api")

# 这两条写法都是"把服务端墙钟当本地墙钟"的直接产物：
#   replace('T', ' ')  把 ISO 串截成字面量，偏移与本地时区都被丢掉
#   getTimezoneOffset() 手工加回偏移，等于把某个国家的时区编进代码
FRONTEND_TIME_PATTERNS = (
    re.compile(r"""replace\(['"]T['"]"""),
    re.compile(r"getTimezoneOffset\(\)"),
)


def _frontend_rel(path: Path) -> str:
    # 门禁测试把 FRONTEND_SRC_DIR 换成 tmp_path 下的假 src 时 relative_to 会抛，退化成文件名即可
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name


def _frontend_source_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in (".vue", ".ts"):
            continue
        if "__tests__" in path.parts:
            continue
        out.append(path)
    return out


def check_frontend_time_entry() -> None:
    """服务端时间的解析必须只走 utils/date.ts，页面不得自行解析或手算偏移。

    第九十五批之前同一份数据有三种互相矛盾的theory并存：utils/date.ts 的注释断言"后端已
    存储北京时间（UTC+8）"并按本地墙钟解析、8 个页面直接 replace('T',' ') 截字面量、
    chat/Detail.vue 手工 +480 分钟。三者各自能解释一种服务端写法，没有一处是错的，合起来
    必然在不同页面上显示成不同时刻。现在解析入口收敛到一个函数，测试覆盖它的契约，本检查
    保证旧写法不再回来。

    局限（不假装覆盖）：这是纯文本门禁，只认这两条字面写法。它不证明其余页面解析正确——
    直接 `new Date(serverStr)` 依赖引擎对无偏移串的口径，而且同一引擎内就不自洽：ES2016 起
    无偏移 date-time 按本地时间解释（ES5 时代按 UTC），纯日期串却一律按 UTC，两种形状方向相反，
    这正是 date.ts 里 NAIVE_RE / DATE_ONLY_RE 两条分支必须存在的原因。门禁也不覆盖 moment/dayjs
    之类第三方格式化，更管不到 java/python 侧写进 DATETIME 的到底是哪个钟。那些要由
    src/utils/__tests__/date.spec.ts 的契约用例与后端批次各自负责。
    """
    offenders: list[str] = []
    scanned = 0
    for name in FRONTEND_TIME_ROOTS:
        root = FRONTEND_SRC_DIR / name
        if not root.is_dir():
            problems.append(f"前端时间入口检查：目录不存在 {_frontend_rel(root)}")
            continue
        for file in _frontend_source_files(root):
            text = file.read_text(encoding="utf-8")
            scanned += 1
            for pattern in FRONTEND_TIME_PATTERNS:
                for lineno, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        offenders.append(
                            f"{_frontend_rel(file)}:{lineno} {line.strip()}"
                        )
    if offenders:
        problems.append(
            "前端自行解析了服务端时间（应改用 utils/date.ts 的入口）:\n    " + "\n    ".join(offenders)
        )
    else:
        print(f"[ok] 前端时间显示只有一个入口：扫描 {scanned} 个文件，未见 replace('T',…) / getTimezoneOffset()")


# ── 检查 13：写侧时钟三源同源，且判定列不读会话钟 ─────────────────────────

APP_YML = REPO / "java-backend" / "src" / "main" / "resources" / "application.yml"
HELM_JAVA_TEMPLATE = HELM_CHART / "templates" / "java.yaml"
HELM_MYSQL_TEMPLATE = HELM_CHART / "templates" / "mysql.yaml"
JAVA_MAIN_JAVA = REPO / "java-backend" / "src" / "main" / "java"
JAVA_MAPPER_XML_DIR = REPO / "java-backend" / "src" / "main" / "resources" / "mapper"

# 同一个 UTC 只能按各自的语法写：MySQL 认 '+00:00'（命名时区要先装 tzinfo 表），
# JVM 认 UTC，Connector/J 两种都收。不归一化就没法谈"三处一致"。
_UTC_TOKENS = {"utc", "z", "gmt", "+0", "+00", "+0000", "+00:00"}

_JVM_TZ_RE = re.compile(r"-Duser\.timezone=([^\s\"']+)")
_MYSQL_TZ_RE = re.compile(r"--default-time-zone=([^\s\"',]+)")
_JDBC_TZ_RE = re.compile(r"[?&]serverTimezone=([A-Za-z0-9_+:%./-]+)")

# 判定列（过期/熔断到点）一旦和会话钟 NOW() 同处一个比较式，同一行的判定就随连接翻转。
_DECISION_COLUMN_NOW_RE = re.compile(
    r"\b(expires_at|recycle_expires_at|circuit_open_until)\b[^\n]*\bNOW\(\)"
)


def _strip_code_comments(text: str) -> str:
    """去掉说明文字，只留代码——注释里同时提到判定列和 NOW() 不算违规。

    块注释整体去掉；行注释只认"整行是注释/续行"的形态，避免把 SQL 字符串里的 `//`
    （如 URL）当注释切断。第九十六批的 mapper 注释就在解释"为什么不用 NOW()"，
    不剥注释的门禁会在自己的说明文字上判红。

    报告里的行号必须指着真正的违规行，所以剥的时候保留行数：注释整行变空行。
    """

    def _blank(match: "re.Match[str]") -> str:
        return "\n" * match.group(0).count("\n")

    text = re.sub(r"<!--.*?-->", _blank, text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", _blank, text, flags=re.DOTALL)
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        kept.append("" if stripped.startswith(("//", "*")) else line)
    return "\n".join(kept)


def _repo_rel(path: Path) -> str:
    """仓库内路径用于报告；门禁测试把常量换成 tmp_path 时 relative_to 会抛，退化成文件名。"""
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name


def _normalized_clock(raw: str | None) -> str | None:
    if raw is None:
        return None
    token = raw.strip().strip("'\"")
    return "UTC" if token.lower() in _UTC_TOKENS else token


def _compose_clock_faces(text: str, service: str) -> dict[str, str | None]:
    """从 compose 的某个服务块里取三张"钟面"：JVM 参数、MySQL 参数、JDBC URL。"""
    block = _compose_service_blocks(text).get(service)
    if block is None:
        return {}
    block = _strip_comments(block)
    jvm = _declared_env(block, "JAVA_TOOL_OPTIONS")
    jdbc = _declared_env(block, "SPRING_DATASOURCE_URL")
    return {
        "jvm": _JVM_TZ_RE.search(jvm).group(1) if jvm and _JVM_TZ_RE.search(jvm) else None,
        "mysql": _MYSQL_TZ_RE.search(block).group(1) if _MYSQL_TZ_RE.search(block) else None,
        "jdbc": _JDBC_TZ_RE.search(jdbc).group(1) if jdbc and _JDBC_TZ_RE.search(jdbc) else None,
    }


def _values_clock_face(text: str, key: str) -> str | None:
    block = _strip_comments(text)
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", block, re.MULTILINE)
    if not m:
        return None
    value = m.group(1)
    for pattern in (_JVM_TZ_RE, _MYSQL_TZ_RE, _JDBC_TZ_RE):
        found = pattern.search(value)
        if found:
            return found.group(1)
    # defaultTimeZone 这类键的值本身就是钟面（"+00:00"），不带旗标
    return value.strip("'\"")


def check_write_clock_caliber() -> None:
    """写侧的三张钟面必须是同一个 UTC，判定列不得读会话钟。

    DATETIME 列存的是字面墙钟，谁写用谁的钟：JVM 默认时区写 LocalDateTime.now()，
    MySQL 的 NOW()/CURRENT_TIMESTAMP 默认值写会话时区的墙钟，Connector/J 再按
    serverTimezone 解释时间戳。第九十六批之前三处都没被任何地方声明钉住，于是同一行
    "是否过期"随连接落在哪个会话而翻转（真库实测：UTC 会话判未过期、+08:00 会话判过期）。

    现在判定 SQL 一律读 UTC_TIMESTAMP()（会话挪不动它），写入侧三处必须同时钉成 UTC——
    只要有一处不是，"判定用 UTC、列里存的是别的墙钟"就以另一种形式回来了。

    局限（不假装覆盖）：纯文本门禁。它证明这三处**声明**了同一个口径，且模板真的读了
    values 里那两个键（否则是没人消费的死配置），但不证明容器起来后 mysqld 真的带上了
    该旗标、也不证明 JVM 真的 Picked up——那两条只在有引擎/集群时可实测，行为侧由
    java-backend 的 WriteClockCaliberTest 在真库上覆盖会话免疫那一半。IT 的 JDBC URL
    一律由 @DynamicPropertySource 注入，生产 URL 上的 serverTimezone 因此只能文本核对。
    """
    bad: list[str] = []
    faces: dict[str, str] = {}

    def note(label: str, raw: str | None) -> None:
        if raw is None:
            bad.append(f"{label} 没有声明时钟口径（未钉 = 随宿主/会话漂）")
            return
        normalized = _normalized_clock(raw)
        faces[label] = normalized
        if normalized != "UTC":
            bad.append(f"{label} 钉的是 {raw}，而判定 SQL 读的是 UTC_TIMESTAMP()")

    def read(path: Path) -> str:
        if not path.is_file():
            bad.append(f"{_repo_rel(path)} 缺失")
            return ""
        return path.read_text(encoding="utf-8")

    for label, path, service in (
        ("dev compose", COMPOSE_DEV, "java-backend"),
        ("dev compose mysql8", COMPOSE_DEV, "mysql8"),
        ("prod compose", COMPOSE_PROD, "java-backend"),
        ("prod compose mysql8", COMPOSE_PROD, "mysql8"),
    ):
        faces_of_service = _compose_clock_faces(read(path), service)
        if not faces_of_service:
            bad.append(f"{label}：找不到服务 {service}")
            continue
        # 只取该服务真正负责的那张钟面：mysql8 没有 JVM，java 侧没有 mysqld 旗标
        # （按 service 分支，不按 label —— label 是给人看的名字，不含服务名）
        if service == "java-backend":
            note(f"{label} JVM", faces_of_service["jvm"])
            note(f"{label} JDBC", faces_of_service["jdbc"])
        else:
            note(f"{label} MySQL", faces_of_service["mysql"])

    values_text = read(HELM_VALUES)
    note("helm javaBackend.javaToolOptions", _values_clock_face(values_text, "javaToolOptions"))
    note("helm mysql.defaultTimeZone", _values_clock_face(values_text, "defaultTimeZone"))

    java_tpl = _strip_comments(read(HELM_JAVA_TEMPLATE))
    mysql_tpl = _strip_comments(read(HELM_MYSQL_TEMPLATE))
    # 键存在但没人引用 = 死配置（第八十三批"模板读了一个不存在的键"的反向形态）
    for template_label, text, key, env in (
        ("templates/java.yaml", java_tpl, ".Values.javaBackend.javaToolOptions", "JAVA_TOOL_OPTIONS"),
        ("templates/mysql.yaml", mysql_tpl, ".Values.mysql.defaultTimeZone", "default-time-zone"),
    ):
        if key not in text:
            bad.append(f"{template_label} 没有引用 {key}（values 里那行没人消费）")
        if env not in text:
            bad.append(f"{template_label} 没有把口径传给容器（缺 {env}）")
    note("helm JDBC", _JDBC_TZ_RE.search(java_tpl).group(1) if _JDBC_TZ_RE.search(java_tpl) else None)

    app_yml = _strip_comments(read(APP_YML))
    note("application.yml 兜底 URL", _JDBC_TZ_RE.search(app_yml).group(1) if _JDBC_TZ_RE.search(app_yml) else None)

    offenders: list[str] = []
    scanned = 0
    for root in (JAVA_MAPPER_XML_DIR, JAVA_MAIN_JAVA):
        if not root.is_dir():
            bad.append(f"{_repo_rel(root)} 缺失")
            continue
        for file in sorted(root.rglob("*")):
            if file.suffix not in (".xml", ".java"):
                continue
            scanned += 1
            code = _strip_code_comments(file.read_text(encoding="utf-8"))
            for lineno, line in enumerate(code.splitlines(), 1):
                if _DECISION_COLUMN_NOW_RE.search(line):
                    offenders.append(
                        f"{_repo_rel(file)}:{lineno} {line.strip()}"
                    )
    if offenders:
        bad.append(
            "判定列读了会话钟 NOW()（应改用 UTC_TIMESTAMP()）:\n    " + "\n    ".join(offenders)
        )

    if bad:
        problems.append("写侧时钟口径不一致:\n    " + "\n    ".join(bad))
    else:
        print(
            f"[ok] 写侧时钟三源同源（{len(faces)} 张钟面全部 = UTC），"
            f"判定列不读会话钟：扫描 {scanned} 个 mapper XML 与 src/main/java 文件"
        )


# ── 检查 14：workflow 的 run 必须是块标量，否则 shell 续行从未生效 ────────

WORKFLOW_DIR = REPO / ".github" / "workflows"
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
EVAL_OFFLINE_SCRIPT = "scripts/eval_offline.py"
EVAL_OFFLINE_ENTRY = REPO / "python-ai" / "scripts" / "eval_offline.py"
EVAL_SUITES_ROOT = REPO / "python-ai" / "evaluation"
# 四个离线冻结套件的调用面：suite(通用) + 招投标三竖门。门禁在这里钉"CI 还在调它们"，
# 套件内容与摘要绑定由 python-ai/tests/test_eval_suite_eol_binding.py 负责。
EVAL_GATE_SUITES = ("suite", "suite_bid", "suite_bid_construction", "suite_bid_it")

_RUN_INLINE_RE = re.compile(r"^(?P<lead>\s*)(?:-\s+)?run:\s+(?P<value>\S.*)$")
_BLOCK_INDICATOR_RE = re.compile(r"^[|>]")
# 续行的形状：既不是 key: 也不是 - item，就只可能是 plain 标量的折行
_YAML_STRUCTURAL_RE = re.compile(r"^\s*(?:-\s+)?[\w][\w.\-]*\s*:(\s|$)|^\s*-\s")


def _run_key_column(line: str) -> int:
    """`run:` 键所在列（列表项写法 `- run:` 再右移两格）。"""
    lead = len(line) - len(line.lstrip())
    if line.lstrip().startswith("- "):
        return lead + 2
    return lead


def _workflow_run_values(path: Path) -> list[tuple[int, str, list[str]]]:
    """返回 [(run: 所在行号, 行内值, 该值之后的更缩进续行), …]，纯文本、不依赖 YAML 库。

    static-checks.py 的约定是只用标准库，所以这里不做完整解析，只回答一个问题：
    这个 `run:` 的值是块标量（`|`/`>`，续行按字面进脚本）还是 plain 标量（换行被折叠成
    空格）。判定按 YAML 的规则做：缩进大于 `run:` 键、又不是 key:/list-item 的紧随行，
    就是 plain 标量的续行。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    found: list[tuple[int, str, list[str]]] = []
    for idx, line in enumerate(lines):
        m = _RUN_INLINE_RE.match(line)
        if not m:
            continue
        key_col = _run_key_column(line)
        continuations: list[str] = []
        for nxt in lines[idx + 1:]:
            if not nxt.strip():
                break
            if len(nxt) - len(nxt.lstrip()) <= key_col:
                break
            if _YAML_STRUCTURAL_RE.match(nxt):
                break
            continuations.append(nxt.strip())
        found.append((idx + 1, m.group("value"), continuations))
    return found


def check_workflow_run_scalars() -> None:
    """CI 的 `run:` 若用行内（plain）标量，续行就永远不会到达 shell。

    第九十七批在真实 CI 上量到的：`run: python scripts/eval_offline.py \\` 后面跟着缩进的
    `--cases …`，YAML 把这当成 plain 多行标量的第一行，折行时把换行折叠成一个空格，于是
    shell 收到的是 `… \\ --cases …`——`\\` 转义的是空格而不是换行。把解析出来的同一串交给
    bash 打印 argv，得到的是 `' --cases'`（前导空格），argparse 认不出选项，退出码 2。
    招投标三个竖门自 2026-08-25（aabd3df6 / f684d6bb）起就是这个形态，从未在 CI 跑过一次。

    因此：带续行的命令必须写成块标量 `run: |`；而只有 `run: |` 里的反斜杠才是 shell 续行。
    """
    bad: list[str] = []
    if not WORKFLOW_DIR.is_dir():
        problems.append(f"检查 14：workflow 目录不存在 {_repo_rel(WORKFLOW_DIR)}")
        return
    files = sorted(p for p in WORKFLOW_DIR.iterdir() if p.suffix in (".yml", ".yaml"))
    if not files:
        problems.append(f"检查 14：{_repo_rel(WORKFLOW_DIR)} 下没有 workflow 文件")
        return

    steps = 0
    for wf in files:
        for lineno, value, conts in _workflow_run_values(wf):
            steps += 1
            if _BLOCK_INDICATOR_RE.match(value):
                continue  # 块标量：反斜杠是真正的 shell 续行
            where = f"{_repo_rel(wf)}:{lineno}"
            if value.rstrip().endswith("\\"):
                bad.append(
                    f"{where} run 用行内标量且以反斜杠收尾——YAML 会折叠换行，"
                    f"shell 收到的是被转义的空格而不是续行：{value[:70]}"
                )
            elif conts:
                bad.append(
                    f"{where} run 用 plain 多行标量（{len(conts)} 条折行），"
                    f"命令会被拼成一行：{value[:50]} … {conts[0][:40]}"
                )

    if not CI_WORKFLOW.is_file():
        bad.append(f"{_repo_rel(CI_WORKFLOW)} 缺失")
    else:
        ci_text = CI_WORKFLOW.read_text(encoding="utf-8")
        for suite in EVAL_GATE_SUITES:
            needle = f"--cases evaluation/{suite}/cases.jsonl"
            if needle not in ci_text:
                bad.append(f"ci.yml 不再调用离线套件 {suite}（{needle}）——门禁消失")
            cases_file = EVAL_SUITES_ROOT / suite / "cases.jsonl"
            if not cases_file.is_file():
                bad.append(f"离线套件用例文件缺失：{_repo_rel(cases_file)}")
        if EVAL_OFFLINE_SCRIPT not in ci_text:
            bad.append(f"ci.yml 里没有任何 {EVAL_OFFLINE_SCRIPT} 调用")
        if not EVAL_OFFLINE_ENTRY.is_file():
            bad.append(f"离线评测入口不存在：{_repo_rel(EVAL_OFFLINE_ENTRY)}（ci.yml 仍在调它）")

    if bad:
        problems.append("workflow run 标量形态不合法:\n    " + "\n    ".join(bad))
    else:
        print(
            f"[ok] workflow run 全部是块标量或单行命令（扫描 {len(files)} 个文件 / {steps} 个 run 步骤），"
            f"四个离线评测门 {', '.join(EVAL_GATE_SUITES)} 仍在 ci.yml 调用且用例文件在位"
        )


# ── 检查 15：python 侧的钟面并入同一 UTC 口径 ────────────────────────────

PYTHON_APP_DIR = REPO / "python-ai" / "app"
HELM_PLUGIN_RUNNER_TEMPLATE = HELM_CHART / "templates" / "plugin-runner.yaml"

# shipped 拓扑里"这是我们的 python 工作负载"的标记：镜像名或 build 的 Dockerfile 名。
# 按标记认而不是按服务名认——服务改名不会让工作负载停止读墙钟。
_PYTHON_WORKLOAD_MARKERS = ("hfusionhub-python", "hfusionhub-plugin-runner", "Dockerfile.plugin-runner")

# 零参的 now()/utcnow()/today() 取的是**进程时区**的墙钟；localtime() 本身就是本地钟；
# fromtimestamp() 少一个 tz 参数就退回本地时区。带参数的 now(UTC) / now(tz=...) 是显式口径，
# 不算违规。
_NAIVE_ZERO_ARG_ATTRS = ("now", "utcnow", "today")
_NAIVE_ALWAYS_ATTRS = ("localtime",)


def _naive_clock_reads(path: Path) -> list[str]:
    """列出一个 .py 文件里的裸本地墙钟读法（`文件:行 代码`）。

    用 ast 而不是正则：文件里的说明文字（docstring/注释）会解释"以前用的是 datetime.now()"，
    正则门禁会在自己的解释上判红，那种红只会教人去删注释。
    """
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{_repo_rel(path)} 解析失败（{exc.msg}），本检查无法核对它的钟面读法"]

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        keywords = {kw.arg for kw in node.keywords if kw.arg}
        if attr in _NAIVE_ALWAYS_ATTRS:
            offenders.append(node.lineno)
        elif attr in _NAIVE_ZERO_ARG_ATTRS and not node.args and not keywords:
            offenders.append(node.lineno)
        elif attr == "fromtimestamp" and len(node.args) < 2 and "tz" not in keywords:
            offenders.append(node.lineno)

    return [
        f"{_repo_rel(path)}:{lineno} {(lines[lineno - 1].strip() if lineno <= len(lines) else '')}"
        for lineno in sorted(set(offenders))
    ]


def _python_workload_labels(text: str, topology: str) -> list[str]:
    """compose 文本里属于我们 python 镜像的工作负载服务名。"""
    found = []
    for name, block in _compose_service_blocks(text).items():
        if any(marker in block for marker in _PYTHON_WORKLOAD_MARKERS):
            found.append(f"{topology} 的服务 {name}")
    return found


def check_python_clock_caliber() -> None:
    """python 侧不许有裸本地墙钟读法，且每个 python 工作负载都要把进程时区钉成 UTC。

    与检查 13 是同一件事的两半：13 钉的是 java 写侧的三张钟面（JVM/MySQL/JDBC），
    这里钉的是 python 的钟面。`datetime.now()` 的零参写法读的是**进程时区**，容器里
    就是宿主/节点的时区——第一百零二批之前没有任何一档拓扑为 python 工作负载声明过
    `TZ`，而 JVM 侧早已三处钉死，于是同一瞬间在两条栈上可以是两个墙钟：TimeTool 给
    模型的"现在几点"随节点漂 8 小时（容器内实测：进程时区翻到 Asia/Shanghai 后输出
    跟着变成 20:14，同一时刻 UTC 是 12:14）。

    两面都要成立：代码显式写 UTC 口径（否则 TZ 一变结果就变），部署声明 TZ=UTC
    （否则第三方库、插件代码、日志格式仍会退回本地钟）。只改代码不钉 TZ，等于把
    正确性押在"全仓库永远没人写裸读法"上；只钉 TZ 不改代码，等于把工具输出的口径
    押在部署上——helm 那档连 values 键都可以不填。

    局限（不假装覆盖）：代码面只扫 python-ai/app，即我们自己的应用码。跑在 plugin-runner
    沙箱里的插件代码不是我们能静态约束的面——约束不了它，才给那个工作负载钉 TZ=UTC。
    零参 `now()` 按方法名匹配、不看接收者类型，别的类恰好有 `now()` 会误报（app 里目前没有）；
    按镜像标记认工作负载，标记改名会红而不是静默漏。部署面证明的是"这三档拓扑声明了同一个
    口径、且模板真的读了 values 键"，不证明 Pod 起来后容器内 `TZ` 真的生效——行为侧由
    python-ai/tests/test_tool_clock_caliber.py 的进程时区免疫用例在 POSIX 上覆盖。
    """
    bad: list[str] = []

    # ── 代码面：app/ 下的裸读法
    scanned = 0
    for root in (PYTHON_APP_DIR,):
        if not root.is_dir():
            bad.append(f"{_repo_rel(root)} 缺失（python 应用目录改名，本检查需同步）")
            continue
        for file in sorted(root.rglob("*.py")):
            scanned += 1
            bad.extend(_naive_clock_reads(file))

    # ── 部署面：compose 两档 + helm 两个模板
    declared: list[str] = []
    for label, path, topology in (
        ("dev compose", COMPOSE_DEV, "docker/docker-compose.yml"),
        ("prod compose", COMPOSE_PROD, "deploy/docker-compose.prod.yml"),
    ):
        if not path.is_file():
            bad.append(f"{label} 缺失：无法核对 python 工作负载的 TZ")
            continue
        text = path.read_text(encoding="utf-8")
        workloads = _python_workload_labels(text, label)
        if not workloads:
            bad.append(
                f"{label}：按 {_PYTHON_WORKLOAD_MARKERS} 没认出任何 python 工作负载"
                "（镜像标记变了，本检查需同步）"
            )
        for name, block in _compose_service_blocks(text).items():
            if f"{label} 的服务 {name}" not in workloads:
                continue
            tz = _declared_env(block, "TZ")
            if tz is None:
                bad.append(
                    f"{label} 的服务 {name} 没有声明 TZ：容器时区跟随宿主，"
                    "naive 读法与依赖库的本地钟会随节点漂"
                )
            elif _normalized_clock(tz) != "UTC":
                bad.append(f"{label} 的服务 {name} 的 TZ={tz}，与 java 写侧的 UTC 口径不一致")
            else:
                declared.append(f"{name}")

    values_text = HELM_VALUES.read_text(encoding="utf-8") if HELM_VALUES.is_file() else ""
    if not values_text:
        bad.append(f"{_repo_rel(HELM_VALUES)} 缺失：无法核对 helm 的 TZ")
    for template_label, template_path, root_key, workload in (
        ("templates/python.yaml", HELM_PYTHON_TEMPLATE, "pythonAi", "python-ai"),
        ("templates/plugin-runner.yaml", HELM_PLUGIN_RUNNER_TEMPLATE, "pluginRunner", "plugin-runner"),
    ):
        if not template_path.is_file():
            bad.append(f"{template_label} 缺失：无法核对 {workload} 的 TZ")
            continue
        tpl = _strip_comments(template_path.read_text(encoding="utf-8"))
        if "TZ" not in tpl:
            bad.append(f"{template_label} 没有把 TZ 传给容器（缺 - name: TZ）")
        key = f".Values.{root_key}.tz"
        if key not in tpl:
            bad.append(f"{template_label} 没有引用 {key}（values 里那行没人消费）")
        # 只认该工作负载自己的根：values 里两个根都叫 tz，在全文件上取第一个会把两边算成同一个值
        section = re.search(
            rf"^{re.escape(root_key)}:\n((?:[ ]+\S.*\n|\n)*)", values_text, re.MULTILINE
        )
        raw = _values_clock_face(section.group(1), "tz") if section else None
        if raw is None:
            bad.append(f"helm values 的 {root_key}.tz 没有声明（未钉 = 随节点漂）")
        elif _normalized_clock(raw) != "UTC":
            bad.append(f"helm values 的 {root_key}.tz={raw}，与 java 写侧的 UTC 口径不一致")
        else:
            declared.append(workload)

    if bad:
        problems.append("python 钟面口径不一致:\n    " + "\n    ".join(bad))
    else:
        print(
            f"[ok] python 钟面口径：{len(declared)} 个 python 工作负载声明 TZ=UTC"
            f"（{', '.join(declared)}），app/ 扫描 {scanned} 个 .py 文件无裸本地墙钟读法"
        )


# ── 检查 16：共享 SQLite 连接的取用与关闭都在 `_db_lock` 内 ───────────────

# 第一百零三／一百零四批本地跑全套件两次踩到解释器级崩溃（退出码 139：一次
# `Windows fatal exception: access violation`、容器里一次 `Fatal Python error:
# Segmentation fault`），崩溃栈点名 `app/core/plugin/audit.py` 的 `_cleanup_synced`。
# 形态是 `db = _get_db()` 写在 `with _db_lock:` **之前**：锁排开了"execute 撞 execute"，
# 却排不开"锁外取到的连接对象 vs `_reset_db()` 的 close()"——线程握住旧对象，等 `_reset_db`
# 放锁后对已关闭的原生句柄 execute，Python 的 `except Exception` 接不住。
# 时序判据只能抽中这种窗口，形态判据不用赌运气，所以在这里钉形。
DB_LOCK_NAME = "_db_lock"
DB_CONN_NAME = "_db_conn"
DB_GETTER_NAME = "_get_db"


def _locked_line_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """每个 `with _db_lock:` 语句体的行号区间（从体内第一条语句到该 with 块末行）。

    起点取体内第一条语句而不是 `with` 那一行：`with` 头部的表达式（这里只有锁名本身）
    不受这把锁保护。副作用是可接受的——`with _db_lock: db = _get_db()` 这种同行写法，
    体首行号就等于 `with` 行号，会被正确判成"在锁内"。
    """
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        guarded = any(
            isinstance(item.context_expr, ast.Name) and item.context_expr.id == DB_LOCK_NAME
            for item in node.items
        )
        if guarded and node.body:
            ranges.append((node.body[0].lineno, node.end_lineno or node.body[-1].end_lineno or 0))
    return ranges


def _db_lock_shape_offenders(source: str, rel: str) -> tuple[list[str], int]:
    """一份源码里"锁外碰共享连接"的行，返回 (违规 `文件:行 代码`, 核对过的引用数)。

    两条规则：
      R1 取连接（`_get_db()`，含 `mod._get_db()` 的属性写法）必须出现在 `with _db_lock:` 体内；
      R2 除 `_get_db` 本体（它只在锁内被调用）以外，任何对 `_db_conn` 的读写也必须在体内——
         `_reset_db` 的 close＋换绑就属于这一类。
    """
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{rel} 解析失败（{exc.msg}），本检查无法核对它的连接生命周期"], 0

    ranges = _locked_line_ranges(tree)

    def inside(lineno: int) -> bool:
        return any(lo <= lineno <= hi for lo, hi in ranges)

    offenders: list[str] = []
    checked = 0
    for node in ast.walk(tree):
        func = getattr(node, "func", None)
        callee = getattr(func, "id", None) or getattr(func, "attr", None)
        if isinstance(node, ast.Call) and callee == DB_GETTER_NAME:
            checked += 1
            if not inside(node.lineno):
                offenders.append(node.lineno)
    # R2 需要按函数排除，单独走一遍 FunctionDef
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if fn.name == DB_GETTER_NAME:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id == DB_CONN_NAME:
                checked += 1
                if not inside(node.lineno):
                    offenders.append(node.lineno)

    return sorted(
        {
            f"{rel}:{lineno} {(lines[lineno - 1].strip() if lineno <= len(lines) else '')}"
            for lineno in set(offenders)
        }
    ), checked


def check_db_lock_lifetime() -> None:
    """审计库那个跨线程共享的 sqlite3 连接，取用与关闭都必须在这把锁内。

    本检查只管形状，不证明没有别的并发缺陷：它读不到 `_flush_stop`/线程生命周期，
    也管不到测试自己起线程绕开封装直接操作连接。行为侧的那一半判据在
    python-ai/tests/test_plugin_audit.py::TestDbConnectionLifetime。
    """
    all_offenders: list[str] = []
    scanned = 0
    references = 0
    if not PYTHON_APP_DIR.is_dir():
        problems.append(f"检查 16：python app 目录不存在 {_repo_rel(PYTHON_APP_DIR)}")
        return
    for path in sorted(PYTHON_APP_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        # 适用面按"有没有碰这三个名字"判，不按"有没有那把锁"判：只认锁名的话，
        # 把 `_db_lock` 连 `with` 一起改掉名就会让整个检查静默变成空扫描。
        if not any(token in source for token in (DB_LOCK_NAME, DB_CONN_NAME, DB_GETTER_NAME)):
            continue
        scanned += 1
        found, checked = _db_lock_shape_offenders(source, _repo_rel(path))
        all_offenders.extend(found)
        references += checked

    if not scanned:
        problems.append(
            f"检查 16 的适用面为空：{_repo_rel(PYTHON_APP_DIR)} 下没有任何文件再引用 "
            f"`{DB_LOCK_NAME}`/`{DB_CONN_NAME}`/`{DB_GETTER_NAME}`——改名或删模块会让这条门静默变绿"
        )
        return

    if all_offenders:
        problems.append(
            "共享 SQLite 连接在 `_db_lock` 外被取用或关闭:\n    " + "\n    ".join(all_offenders)
        )
    else:
        print(
            f"[ok] 审计连接生命周期：扫描 {scanned} 个碰共享连接的模块、"
            f"{references} 处引用，全部在 `with {DB_LOCK_NAME}:` 体内"
        )


# ── 检查 17：Flyway 步骤必须把插件真读的那三个值传到命令行上 ──────────────

JAVA_POM = REPO / "java-backend" / "pom.xml"

# flyway-maven-plugin 的连接配置只认 `-Dflyway.url/user/password`、`flyway.conf` 或
# `FLYWAY_*` 环境变量，**不**认 Spring 的 `SPRING_DATASOURCE_*`。第一百零八批的对象就是
# 把连接信息只写进 Spring 键的那三处站点：步骤从诞生起就死在
# `FlywayException: Unable to connect to the database. Configure the url, user and password!`
FLYWAY_CONNECTION_FLAGS = ("-Dflyway.url=", "-Dflyway.user=", "-Dflyway.password=")
SPRING_DB_KEYS = ("SPRING_DATASOURCE_URL", "SPRING_DATASOURCE_USERNAME", "SPRING_DATASOURCE_PASSWORD")

# 每个 workflow 里应当存在的 flyway 调用数（存在性也钉住——处置不得退化成"把红的那一步删掉"）。
# ci.yml 是 1 个 migrate + 1 个 info；e2e.yml 两个 job 各 1 个 migrate；eval-nightly.yml 1 个。
FLYWAY_STEP_EXPECTATIONS = {"ci.yml": 2, "e2e.yml": 2, "eval-nightly.yml": 1}

_FLYWAY_GOAL_RE = re.compile(
    r"flyway:(?:migrate|info|validate|clean|undo|baseline|repair)\b"
)
# 步骤起始行：`- <key>:` 才算（`- 22` 这类矩阵元素不是步骤，把它当边界会把步骤块切碎）
_STEP_START_RE = re.compile(r"^(?P<indent> *)- (?P<key>[\w.-]+):(?P<rest>.*)$")


def _step_block(lines: list[str], idx: int, indent: str) -> list[str]:
    """一个步骤的文本范围：从 `- name:` 那行起，到下一条缩进不大于它的非空行为止。

    按缩进切而不是按"下一个 `- xxx:`"切，是因为步骤块后面可能紧跟 job 级的键
    （`  frontend:`）或 `defaults:` 里的 `run:`——它们都不是这个步骤的组成部分，
    把后者当 `run:` 读会让真正的脚本正文被空值覆盖。
    """
    width = len(indent)
    for j in range(idx + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= width:
            return lines[idx:j]
    return lines[idx:]


def _step_key(block: list[str], key_col: int, key: str) -> tuple[int, str]:
    """步骤自己的那个键，返回 (块内行号, 行内值)；没有则 (-1, "")。

    键要么正好落在 `key_col` 这一列，要么就挂在起始那个 `- ` 列表符后面（`- name:` 的
    `name` 前面是 6 个空格加 `- `，不是 8 个空格）——只按纯缩进匹配会把步骤名读成空。
    只认这一列的键：job 的 `defaults:` 里也有 `run:`，把它当成步骤脚本读，
    真正的脚本正文就会被一个空值盖掉（第一百零八批写这条门时先踩过一次）。
    """
    pattern = re.compile(
        "^(?:" + " " * key_col + "|" + " " * (key_col - 2) + r"- )"
        + re.escape(key) + r":(?P<value>.*)$"
    )
    for offset, line in enumerate(block):
        match = pattern.match(line)
        if match:
            return offset, match.group("value").strip()
    return -1, ""


def _workflow_steps(path: Path) -> list[dict]:
    """把 workflow 文本切成步骤，返回 [{name, lineno, env, run}, …]，纯文本、不依赖 YAML 库。

    `run:` 只解两种现行形态：块标量（`|`/`>`，取更深缩进的正文，**不含标量指示符本身**——
    YAML 解析出的值里也没有它）与单行内联。带续行的行内标量由检查 14 单独判红，这里不重复它的结论。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    steps: list[dict] = []
    for idx, line in enumerate(lines):
        match = _STEP_START_RE.match(line)
        if not match:
            continue
        indent = match.group("indent")
        block = _step_block(lines, idx, indent)
        key_col = len(indent) + 2

        _, name = _step_key(block, key_col, "name")
        env_offset, _ = _step_key(block, key_col, "env")
        run_offset, run_value = _step_key(block, key_col, "run")

        env_rows: list[str] = []
        if env_offset >= 0:
            for nxt in block[env_offset + 1:]:
                if not nxt.strip() or len(nxt) - len(nxt.lstrip()) <= key_col:
                    break
                env_rows.append(nxt)

        run_text = run_value
        if run_offset >= 0 and run_value[:1] in ("|", ">"):
            body: list[str] = []
            for nxt in block[run_offset + 1:]:
                if not nxt.strip():
                    body.append("")
                    continue
                if len(nxt) - len(nxt.lstrip()) <= key_col:
                    break
                body.append(nxt.strip())
            run_text = "\n".join(body)

        steps.append({
            "name": name,
            "lineno": idx + 1,
            "env": "\n".join(env_rows),
            "run": run_text,
            "soft": any("continue-on-error: true" in b for b in block),
        })
    return steps


def _flyway_offenders(wf_files: list[Path]) -> tuple[list[str], int]:
    """返回 (违规清单, 核对到的 flyway 调用数)。"""
    offenders: list[str] = []
    counts: dict[str, int] = {}
    for wf in wf_files:
        counted = 0
        for step in _workflow_steps(wf):
            if not _FLYWAY_GOAL_RE.search(step["run"]):
                continue
            counted += 1
            where = f"{_repo_rel(wf)}:{step['lineno']}（步骤 {step['name'] or '未命名'}）"
            missing = [
                flag for flag in FLYWAY_CONNECTION_FLAGS
                if not re.search(re.escape(flag) + r"\S", step["run"])
            ]
            if missing:
                offenders.append(
                    f"{where} 命令行缺 {', '.join(missing)}——flyway-maven-plugin 不读别的名字，"
                    "拿到空配置就报 `Unable to connect to the database`"
                )
            dead = [key for key in SPRING_DB_KEYS if key in step["env"]]
            if dead:
                offenders.append(
                    f"{where} 的连接信息写成了 {', '.join(dead)}——插件不读 Spring 的键，"
                    "这三个值是空转的开关"
                )
            if step["soft"]:
                offenders.append(f"{where} 带 `continue-on-error: true`——迁移失败必须让 job 红")
        counts[wf.name] = counts.get(wf.name, 0) + counted

    for filename, expected in FLYWAY_STEP_EXPECTATIONS.items():
        actual = counts.get(filename, 0)
        if actual != expected:
            offenders.append(
                f"{filename} 里 flyway 调用数是 {actual}，预期 {expected}——"
                "步骤被删或被改名会让这条门只剩「没东西可查」的空绿"
            )

    pom_offenders = _flyway_plugin_pin_offenders()
    offenders.extend(pom_offenders)
    return offenders, sum(counts.values())


def _flyway_plugin_pin_offenders() -> list[str]:
    """pom 必须显式声明 flyway-maven-plugin，且版本指向运行时那个 flyway。

    没有声明时 `mvn flyway:migrate` 走 Maven 前缀解析，每次从 central 取**当时最新**版本
    （日志里就出现过 `flyway:11.7.2` ＋两条 metadata 401 噪声）——插件版本与运行时
    `flyway-core`（由 spring-boot-starter-parent 的 `flyway.version` 管理）分家，
    同一条迁移链可能被两个大版本解释。所以钉的是 `${flyway.version}` 这个**引用**，
    不是某个数字字面量：写字面量等于把同源关系复制成两处会各自漂移的常量。
    """
    if not JAVA_POM.is_file():
        return [f"{_repo_rel(JAVA_POM)} 缺失，无法核对 flyway-maven-plugin 的钉版"]
    pom = JAVA_POM.read_text(encoding="utf-8")
    block = re.search(
        r"<plugin>\s*<groupId>org\.flywaydb</groupId>\s*"
        r"<artifactId>flyway-maven-plugin</artifactId>(.*?)</plugin>",
        pom,
        re.S,
    )
    if not block:
        return [
            "java-backend/pom.xml 没有声明 flyway-maven-plugin——`mvn flyway:migrate` 会按前缀"
            "浮动解析最新版本，与运行时 flyway-core 不同源"
        ]
    version_match = re.search(r"<version>([^<]*)</version>", block.group(1))
    if not version_match:
        return ["pom 的 flyway-maven-plugin 没有 <version>——仍然是浮动解析"]
    version = version_match.group(1).strip()
    if version == "${flyway.version}":
        return []
    return [
        f"pom 的 flyway-maven-plugin 钉的是 `{version}`，不是 `${{flyway.version}}`——"
        "写成数字就把「插件与运行时 flyway 同版本」这件事从结构保证降级成一次人工同步"
    ]


def check_flyway_cli() -> None:
    """CI 里每一次 flyway 调用都必须传插件真读的旗标，且插件版本与运行时同源。

    行为侧的判据不在这里：本检查只管 workflow 文本与 pom 的形状。"迁移确实发生"是
    第一百零八批在活 MySQL 8.0.46 上按同一行命令实测的（87 条迁移全部应用，
    `flyway_schema_history` 87 行 success=1，schema 落到 v86），
    证据记在 CHANGELOG 与 docs/CI_GATES.md，不由这条文本门冒充。
    """
    if not WORKFLOW_DIR.is_dir():
        problems.append(f"检查 17：workflow 目录不存在 {_repo_rel(WORKFLOW_DIR)}")
        return
    wf_files = sorted(p for p in WORKFLOW_DIR.iterdir() if p.suffix in (".yml", ".yaml"))
    if not wf_files:
        problems.append(f"检查 17：{_repo_rel(WORKFLOW_DIR)} 下没有 workflow 文件")
        return

    offenders, calls = _flyway_offenders(wf_files)
    if not calls:
        problems.append(
            f"检查 17 的适用面为空：没有任何 workflow 再调用 flyway——"
            f"删掉这些步骤或把 goal 改名会让这条门静默变绿（预期 {FLYWAY_STEP_EXPECTATIONS}）"
        )
        return
    if offenders:
        problems.append("Flyway 命令行/钉版形态不合法:\n    " + "\n    ".join(offenders))
    else:
        print(
            f"[ok] Flyway 命令行旗标：扫描 {len(wf_files)} 个 workflow / {calls} 处 flyway 调用，"
            f"全部显式传 {', '.join(flag.rstrip('=') for flag in FLYWAY_CONNECTION_FLAGS)}，"
            "且 pom 把 flyway-maven-plugin 钉到 ${flyway.version}"
        )


# ── 检查 18：容器轨的两条"配置写了，但容器里没有对应实体"契约 ────────────────

COMPOSE_TOPOLOGIES = (
    ("docker/docker-compose.yml", COMPOSE_DEV),
    ("deploy/docker-compose.prod.yml", COMPOSE_PROD),
)

# 规则③的下界（只防"越扫越少"，不防新增：新属性若没并进同一个环境变量，配对规则自然红）
PYTHON_BASE_URL_MIN_PROPERTIES = 3
PYTHON_BASE_URL_MIN_SITES = 10
PYTHON_BASE_URL_RE = re.compile(
    r'@Value\("\$\{([A-Za-z0-9_.-]+):(https?://[^/"}\s]+:9000[^/"}\s]*)\}"\)'
)
# java→python 出站地址在三个部署面上的落点（compose 取服务块，helm 取整份模板）
PYTHON_BASE_URL_TOPOLOGIES = (
    ("docker/docker-compose.yml", COMPOSE_DEV, "java-backend"),
    ("deploy/docker-compose.prod.yml", COMPOSE_PROD, "java-backend"),
    ("deploy/helm/hfusionhub/templates/java.yaml", HELM_JAVA_TEMPLATE, None),
)

# 预期适用面：数量漂移=前提变了，必须先响，不能悄悄变成空扫描。
#   ARQ_WORKER_SERVICES：dev 拓扑恰有一个 `python -m arq` worker 服务
#   REDIS_CLIENT_SERVICES：两拓扑各有一个声明 SPRING_DATA_REDIS_HOST 的 java 工作负载
ARQ_WORKER_SERVICES = {"docker/docker-compose.yml": 1}
REDIS_CLIENT_SERVICES = {
    "docker/docker-compose.yml": 1,
    "deploy/docker-compose.prod.yml": 1,
}
REDIS_PASSWORD_KEYS = ("SPRING_DATA_REDIS_PASSWORD", "REDIS_PASSWORD")
ARQ_SETTINGS_SUFFIX = ".WorkerSettings"


def _dockerfile_final_stage(text: str) -> str:
    """Dockerfile 的运行阶段（最后一个 FROM 段）——只有它决定容器里最终有什么。"""
    stages = re.split(r"^FROM\b", _strip_comments(text), flags=re.MULTILINE)[1:]
    return stages[-1] if stages else ""


def _command_tokens(block: str) -> list[str]:
    """服务块里的 command，兼容 flow 列表与短横列表两种 YAML 写法。"""
    text = _strip_comments(block)
    flow = re.search(r"^\s*command:\s*\[(.*)\]\s*$", text, re.MULTILINE)
    if flow:
        return [tok.strip().strip("'\"") for tok in flow.group(1).split(",")]
    head = re.search(r"^\s*command:\s*$", text, re.MULTILINE)
    if not head:
        return []
    key_indent = len(head.group(0)) - len(head.group(0).lstrip())
    tokens: list[str] = []
    item_indent: int | None = None
    for line in text[head.end() :].splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        item = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if item is None or indent <= key_indent:
            break
        if item_indent is None:
            item_indent = indent
        elif indent != item_indent:
            break
        tokens.append(item.group(1).strip("'\""))
    return tokens


def _arq_entry_module(tokens: list[str]) -> tuple[str | None, str | None]:
    """`python -m arq <模块>.WorkerSettings` 里的模块路径，返回 (模块, 形状问题)。"""
    for idx, token in enumerate(tokens):
        if token != "-m" or idx + 1 >= len(tokens) or tokens[idx + 1] != "arq":
            continue
        for arg in tokens[idx + 2 :]:
            if arg.startswith("-"):
                continue
            if arg.endswith(ARQ_SETTINGS_SUFFIX):
                return arg[: -len(ARQ_SETTINGS_SUFFIX)], None
            return None, f"arq 的入口参数 {arg!r} 不是 `<模块>{ARQ_SETTINGS_SUFFIX}` 形状"
        return None, "命令里有 `-m arq` 但没有入口参数"
    return None, None


def _copy_instructions(text: str) -> list[tuple[str, str]]:
    """运行阶段的 COPY，展开成 [(源, 目标)]；`--from=`/`--chmod=` 等旗标先丢掉。"""
    pairs: list[tuple[str, str]] = []
    for line in _dockerfile_final_stage(text).splitlines():
        matched = re.match(r"^COPY\s+(.*)$", line.strip())
        if matched is None:
            continue
        parts = [tok for tok in matched.group(1).split() if not tok.startswith("--")]
        if len(parts) < 2:
            continue
        *sources, target = parts
        pairs.extend((src, target) for src in sources)
    return pairs


def _image_top_level_names(dockerfile: Path) -> set[str]:
    """镜像在 WORKDIR 上可直接 import 的顶层名字，只认仓内实际用的两种 COPY 形状。

    `COPY app/ app/` ⇒ 包 app（源与目标基名同号）；`COPY x.py .` ⇒ 顶层模块 x。
    落到 WORKDIR 之外或另有目标名的形状一律不计入：这个集合只用来证明"覆盖"，
    少判只会让门变红，不会让门变绿。
    """
    text = dockerfile.read_text(encoding="utf-8")
    workdirs = re.findall(
        r"^WORKDIR\s+(\S+)\s*$", _dockerfile_final_stage(text), re.MULTILINE
    )
    roots = {".", ""}
    if workdirs:
        roots.add(workdirs[-1].strip("/"))
    names: set[str] = set()
    for src, target in _copy_instructions(text):
        source = src.rstrip("/")
        dest = target.rstrip("/")
        if source.endswith(".py"):
            if dest in roots:
                names.add(Path(source).stem)
            continue
        if "." in Path(source).name or "/" in dest:
            continue
        if dest == Path(source).name:
            names.add(dest)
    return names


def _service_build_paths(block: str, compose_path: Path) -> tuple[Path | None, Path | None]:
    """服务块里的 build.context 与 build.dockerfile，解析成仓库内的绝对路径。

    Compose 规范里 `dockerfile` 相对于 `context`，dev/prod 两份都按这条写
    （context=../python-ai，dockerfile=../deploy/Dockerfile.python ⇒ deploy/）。
    """
    text = _strip_comments(block)
    context = re.search(r"^\s+context:\s*(\S+)\s*$", text, re.MULTILINE)
    if context is None:
        return None, None
    ctx = (compose_path.parent / context.group(1)).resolve()
    dockerfile = re.search(r"^\s+dockerfile:\s*(\S+)\s*$", text, re.MULTILINE)
    df = (ctx / dockerfile.group(1)).resolve() if dockerfile else (ctx / "Dockerfile")
    return ctx, df


def _module_covered(module: str, names: set[str]) -> bool:
    if "." in module:
        return module.split(".", 1)[0] in names
    return module in names


def _worker_module_offenders() -> tuple[list[str], int]:
    """规则①：compose 的 command 引用的 python 模块必须真在该服务镜像的 COPY 集合里。"""
    offenders: list[str] = []
    found: dict[str, int] = {}
    for label, path in COMPOSE_TOPOLOGIES:
        if not path.is_file():
            offenders.append(f"{label} 不存在：{path}")
            continue
        blocks = _compose_service_blocks(path.read_text(encoding="utf-8"))
        for service, block in sorted(blocks.items()):
            module, shape_problem = _arq_entry_module(_command_tokens(block))
            if shape_problem is not None:
                offenders.append(f"{label}/{service}: {shape_problem}")
                found[label] = found.get(label, 0) + 1
                continue
            if module is None:
                continue
            found[label] = found.get(label, 0) + 1
            ctx, dockerfile = _service_build_paths(block, path)
            if ctx is None or dockerfile is None:
                offenders.append(
                    f"{label}/{service}: command 引用 {module}，但该服务没有 build.context，"
                    "无从核对镜像里到底有什么"
                )
                continue
            if not dockerfile.is_file():
                offenders.append(f"{label}/{service}: Dockerfile 不存在 {dockerfile}")
                continue
            names = _image_top_level_names(dockerfile)
            if not _module_covered(module, names):
                offenders.append(
                    f"{label}/{service}: `{module}{ARQ_SETTINGS_SUFFIX}` 不在 {dockerfile.name} "
                    f"的 COPY 派生顶层模块 {sorted(names)} 里——容器内死于 "
                    f"ModuleNotFoundError: No module named '{module}'，而失败点在队列侧"
                    "（job 滞留、解析永不回调），API 层看着一切正常"
                )
                continue
            source = ctx / f"{module.replace('.', '/')}.py"
            if not source.is_file():
                offenders.append(f"{label}/{service}: 构建上下文里没有 {source}（COPY 的源不存在）")
    for label, expected in ARQ_WORKER_SERVICES.items():
        got = found.get(label, 0)
        if got != expected:
            offenders.append(
                f"{label} 里 `python -m arq` 的 worker 服务数 = {got}，预期 {expected}"
                "（适用面漂移：删掉该服务或改掉命令形状会让这条规则不再检查任何东西）"
            )
    return offenders, sum(found.values())


def _redis_auth_offenders() -> tuple[list[str], int]:
    """规则②：拓扑里的 redis 起 `--requirepass` 时，连它的 java 工作负载必须成对给 host＋密码。

    helm 不在适用面上：deploy/helm/hfusionhub/templates/redis.yaml 的 redis 容器没有
    requirepass（第一百零九批核对），java.yaml 因此只需 host。日后 helm 给 redis 上密码，
    要把该拓扑并进 COMPOSE_TOPOLOGIES 同类的扫描清单。
    """
    offenders: list[str] = []
    clients = 0
    for label, path in COMPOSE_TOPOLOGIES:
        if not path.is_file():
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        if "--requirepass" not in text:
            continue
        blocks = _compose_service_blocks(text)
        hosts = sorted(
            service
            for service, block in blocks.items()
            if _declared_env(block, "SPRING_DATA_REDIS_HOST") is not None
        )
        for service in hosts:
            clients += 1
            block = blocks[service]
            if all(_declared_env(block, key) is None for key in REDIS_PASSWORD_KEYS):
                offenders.append(
                    f"{label}/{service}: 该拓扑的 redis 以 --requirepass 启动，工作负载声明了 "
                    f"SPRING_DATA_REDIS_HOST 却没声明 {' 或 '.join(REDIS_PASSWORD_KEYS)} "
                    "里的任何一个——Sa-Token 会话存进的就是这个 redis，握手失败落在第一个"
                    "要用会话的接口上（第一百零九批实测：登录 500 "
                    "RedisConnectionFailureException）"
                )
        expected = REDIS_CLIENT_SERVICES.get(label)
        if expected is not None and len(hosts) != expected:
            offenders.append(
                f"{label} 里声明 SPRING_DATA_REDIS_HOST 的工作负载数 = {len(hosts)}，"
                f"预期 {expected}（适用面漂移）"
            )
    if clients == 0:
        offenders.append(
            "检查 18 规则②的适用面为空：没有任何 compose 拓扑再以 --requirepass 起 redis——"
            "去掉密码或把旗标改名会让这条门静默变绿"
        )
    return offenders, clients


def _flatten_yaml_scalars(text: str) -> dict[str, str]:
    """application.yml 的标量按 `a.b.c` 摊平（两空格缩进、只认 `key: value` 行）。

    只为规则③服务：Spring 的 `@Value("${python-ai.engine.url:...}")` 对应的 yml 键是嵌套的，
    按点号路径查才能对上。列表、多行标量与锚点不参与——那些形状里放的不是出站地址。
    """
    flat: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if not line.strip() or line.lstrip().startswith("-"):
            continue
        matched = re.match(r"^([A-Za-z0-9_.-]+):(.*)$", line.strip())
        if matched is None:
            continue
        indent = len(line) - len(line.lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key, value = matched.group(1), matched.group(2).strip()
        path = ".".join([*[name for _, name in stack], key])
        if value:
            flat[path] = value.strip("'\"")
        else:
            stack.append((indent, key))
    return flat


def _java_python_base_url_sites() -> list[tuple[str, str, str]]:
    """java 侧读来当 python 出站基址的 @Value 位点：(文件, 属性名, 代码里的缺省值)。"""
    if not JAVA_MAIN_JAVA.is_dir():
        return []
    sites: list[tuple[str, str, str]] = []
    for path in sorted(JAVA_MAIN_JAVA.rglob("*.java")):
        text = _strip_code_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for matched in PYTHON_BASE_URL_RE.finditer(text):
            sites.append((_repo_rel(path), matched.group(1), matched.group(2)))
    return sites


def _python_base_url_offenders() -> tuple[list[str], int]:
    """规则③：java→python 的出站基址属性必须全部由同一个环境变量喂，且三档拓扑都设了它。

    第一百零九批实测的形状是"键名不同、来源也不同"：`ai-service.base-url` 写成
    `${AI_SERVICE_URL:...}`，而 `python-ai.base-url` / `python-ai.engine.url` 是裸字面量
    `http://localhost:9000`；三档拓扑只设 AI_SERVICE_URL，于是容器里 java 调 python 的解析
    请求打到 java 自己身上（POST /api/document/204/parse → 400 I/O error，
    traceId 9dae81714a9a41a1812c0cb3155fca89）。
    """
    offenders: list[str] = []
    sites = _java_python_base_url_sites()
    if not sites:
        return [
            "检查 18 规则③的适用面为空：java 侧再没有任何 @Value 以 python 的 :9000 地址作缺省值——"
            "整族改名会让这条门静默变绿"
        ], 0
    properties = sorted({prop for _, prop, _ in sites})
    if len(properties) < PYTHON_BASE_URL_MIN_PROPERTIES or len(sites) < PYTHON_BASE_URL_MIN_SITES:
        offenders.append(
            f"规则③的适用面缩小了：{len(sites)} 处 @Value / {len(properties)} 个属性，"
            f"预期至少 {PYTHON_BASE_URL_MIN_SITES} 处 / {PYTHON_BASE_URL_MIN_PROPERTIES} 个"
            f"（现存属性：{properties}）"
        )
    if not APP_YML.is_file():
        return [*offenders, f"application.yml 不存在：{APP_YML}"], len(sites)

    flat = _flatten_yaml_scalars(APP_YML.read_text(encoding="utf-8"))
    env_names: set[str] = set()
    for prop in properties:
        value = flat.get(prop)
        if value is None:
            where = next(file for file, name, _ in sites if name == prop)
            offenders.append(
                f"application.yml 里没有 {prop}（{where} 在读它）——只能靠 @Value 的代码缺省值，"
                "而那个缺省值是宿主地址"
            )
            continue
        referenced = re.match(r"^\$\{([A-Z0-9_]+)(?::([^}]*))?\}$", value)
        if referenced is None:
            offenders.append(
                f"application.yml 的 {prop} = {value!r} 是裸字面量：拓扑改不动它，容器里必然指回 "
                "java 自己的 localhost（第一百零九批实测：POST /api/document/204/parse 400 "
                'I/O error on POST "http://localhost:9000/api/parse"）'
            )
            continue
        env_names.add(referenced.group(1))

    if len(env_names) > 1:
        offenders.append(
            f"这些出站地址属性各自引用不同的环境变量 {sorted(env_names)}——拓扑只需设其中一个，"
            "另一个就静默留回宿主缺省值"
        )
        return offenders, len(sites)
    if not env_names:
        return offenders, len(sites)

    shared = next(iter(env_names))
    for label, path, service in PYTHON_BASE_URL_TOPOLOGIES:
        if path is None or not path.is_file():
            offenders.append(f"{label} 不存在，无从核对 {shared} 是否声明")
            continue
        text = path.read_text(encoding="utf-8")
        if service is None:
            block = text
        else:
            block = _compose_service_blocks(_strip_comments(text)).get(service, "")
            if not block:
                offenders.append(f"{label} 里没有服务 {service}，无从核对 {shared}")
                continue
        if _declared_env(block, shared) is None:
            offenders.append(
                f"{label}: java 工作负载没有声明 {shared}，而 application.yml 的出站地址全靠它"
            )
    return offenders, len(sites)


def _image_probe_port(dockerfile: Path | None) -> str | None:
    """镜像 HEALTHCHECK 打的端口——它描述的是 CMD 那个进程，不是任意换 command 的进程。

    真仓库那行是带 `\\` 续行的（deploy/Dockerfile.python:52），URL 在下一物理行上，
    所以先把续行拼成一条逻辑行再找——否则端口恒为 None，"自定义探针仍打服务端口"
    那一支就永远不触发。
    """
    if dockerfile is None or not dockerfile.is_file():
        return None
    logical = re.sub(r"\\\s*\n", " ", _dockerfile_final_stage(dockerfile.read_text(encoding="utf-8")))
    matched = re.search(
        r"^HEALTHCHECK.*?://[^/\s:]+:(\d+)",
        logical,
        re.MULTILINE,
    )
    return matched.group(1) if matched else None


def _healthcheck_block(block: str) -> str | None:
    """服务块里的 healthcheck 正文；键不存在返回 None（那就意味着继承镜像的探针）。"""
    text = _strip_comments(block)
    head = re.search(r"^\s*healthcheck:\s*$", text, re.MULTILINE)
    if head is None:
        return None
    key_indent = len(head.group(0)) - len(head.group(0).lstrip())
    lines: list[str] = []
    for line in text[head.end() :].splitlines():
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= key_indent:
            break
        lines.append(line)
    return "\n".join(lines)


def _worker_health_offenders() -> tuple[list[str], int]:
    """规则④：跑 arq worker 的服务不得用 HTTP 存活探针——它不监听那个端口。"""
    offenders: list[str] = []
    checked = 0
    for label, path in COMPOSE_TOPOLOGIES:
        if not path.is_file():
            continue
        blocks = _compose_service_blocks(_strip_comments(path.read_text(encoding="utf-8")))
        for service, block in sorted(blocks.items()):
            module, _ = _arq_entry_module(_command_tokens(block))
            if module is None:
                continue
            checked += 1
            _, dockerfile = _service_build_paths(block, path)
            port = _image_probe_port(dockerfile)
            health = _healthcheck_block(block)
            if health is None:
                offenders.append(
                    f"{label}/{service}: command 是 `python -m arq`，但服务没写 healthcheck，"
                    f"于是继承镜像里给 HTTP 进程写的探针（:{port}）——容器 running、心跳在写，"
                    "状态却永久 unhealthy（第一百零九批实测：probe_http=000、curl exit=7），"
                    "真正要看的崩溃循环反而被这片假红盖住"
                )
                continue
            if re.search(r"^\s*disable:\s*true\s*$", health, re.MULTILINE):
                continue
            if port and f":{port}" in health:
                offenders.append(
                    f"{label}/{service}: worker 的自定义 healthcheck 仍在打 :{port} 的 HTTP 面，"
                    "而 arq 进程不监听它——要么 disable，要么换成真正的存活信号（如队列心跳）"
                )
    if checked == 0:
        offenders.append(
            "检查 18 规则④的适用面为空：没有任何拓扑再以 command 起 arq worker——"
            "删掉 worker 服务会让这条门静默变绿"
        )
    return offenders, checked


def check_container_runtime_contract() -> None:
    """检查 18：容器轨上"配置写了、实体或语义对不上"的四类断链。

    四条都是第一百零九批在 fullstack 整栈上第一次跑出来的，不是假想：
      ① `python-ai-worker` 的 command 是 `python -m arq arq_worker.WorkerSettings`，
         而改前的 deploy/Dockerfile.python 只 COPY 了 app/ ⇒ 容器内 ModuleNotFoundError，
         崩溃循环 14 次，`arq:queue` 里的 job 滞留 83s 无人消费（API 层全程正常）。
      ② dev compose 的 redis7 以 `--requirepass "$REDIS_PASSWORD"` 启动，java-backend
         只给了 SPRING_DATA_REDIS_HOST，登录接口 500 RedisConnectionFailureException；
         prod compose 同一段一直是成对的（deploy/docker-compose.prod.yml:176）。
      ③ application.yml 的 python-ai.base-url / python-ai.engine.url 曾是裸字面量，
         三档拓扑只设 AI_SERVICE_URL ⇒ java 调 python 的解析请求打到自己身上（400）。
      ④ worker 继承镜像里给 HTTP 进程写的 HEALTHCHECK ⇒ 永久 unhealthy，
         真信号（进程退出/崩溃循环）被这片假红盖住。
    共同形状是"起得来、健康检查不红，但链路在别处断"，所以钉成文本门。
    """
    worker_offenders, worker_commands = _worker_module_offenders()
    auth_offenders, auth_clients = _redis_auth_offenders()
    url_offenders, url_sites = _python_base_url_offenders()
    health_offenders, health_checked = _worker_health_offenders()
    offenders = worker_offenders + auth_offenders + url_offenders + health_offenders
    if offenders:
        problems.append("容器轨的运行期契约不成立:\n    " + "\n    ".join(offenders))
    else:
        print(
            f"[ok] 容器轨运行期契约：{worker_commands} 处 `python -m arq` 入口模块都被其 Dockerfile "
            f"的 COPY 集合覆盖、且已脱离 HTTP 探针（{health_checked} 个 worker）；"
            f"{auth_clients} 个连 requirepass redis 的 java 工作负载成对声明了 host＋密码键；"
            f"{url_sites} 处 java→python 出站地址同源于一个环境变量，三档拓扑都声明了它"
        )


# ── 检查 19：e2e 轨上"测试步骤在、监听 :3000 的进程不在" ──────────────────────

E2E_WORKFLOW = WORKFLOW_DIR / "e2e.yml"
PLAYWRIGHT_CONFIG = REPO / "hfusionhub-frontend" / "playwright.config.ts"

# 预期适用面（下界，只防"越扫越少"）：e2e.yml 的两个 job 各一条 `npx playwright test`
# —— e2e-smoke 走 PR、e2e-full 走 push。少一个就是那条链没人核了。
E2E_TEST_JOBS = {"e2e-smoke", "e2e-full"}

_FRONTEND_SERVE_RE = re.compile(r"npm run (?:dev|preview)\b[^\n]*&\s*$", re.MULTILINE)
_NPM_CI_RE = re.compile(r"\bnpm ci\b")
_PLAYWRIGHT_TEST_RE = re.compile(r"npx playwright test\b")
_PROBE_URL_RE = re.compile(r"https?://[A-Za-z0-9_.-]+:(\d+)")


def _workflow_job_ranges(path: Path) -> list[tuple[str, int, int]]:
    """`jobs:` 下每个 job 的行号区间 [(名称, 起, 止)]——步骤要按 job 归属才谈得上先后。

    只认 2 空格缩进的那一列：job 内部的 `services:`/`steps:` 在 4 空格、步骤项在 6 空格，
    都不是 job 名；`on:` 块里也有一批 2 空格键，靠 `jobs:` 这个开关挡住。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts: list[tuple[str, int]] = []
    in_jobs = False
    for idx, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            in_jobs = line.strip() == "jobs:"
            continue
        if in_jobs and len(line) - len(line.lstrip()) == 2:
            matched = re.match(r"^  ([\w.-]+):", line)
            if matched:
                starts.append((matched.group(1), idx))
    return [
        (name, start, starts[i + 1][1] if i + 1 < len(starts) else len(lines))
        for i, (name, start) in enumerate(starts)
    ]


def _playwright_base_url_port(text: str) -> str | None:
    """测试端真正去的端口——`baseURL` 里那个，不是别处写的数。"""
    matched = re.search(r"baseURL:[^\n]*?://[A-Za-z0-9_.-]+:(\d+)", text)
    return matched.group(1) if matched else None


def _playwright_ci_autostarts(text: str) -> bool:
    """CI 档下 Playwright 是否自己起前端。

    真仓库写的是跨三行的三元式（`webServer: CI` / `? undefined` / `: {…}`，
    playwright.config.ts:31-38），所以先把空白压平成一条逻辑行再匹配——
    这是第一百零九批检查 18 那条续行教训的同一条规则。压平后只看 `CI ?` 之后第一个
    非空 token：`undefined` 就是不自起，`{` 或别的都是自起。
    """
    flat = re.sub(r"\s+", " ", text)
    matched = re.search(r"webServer: (?:CI \? )?(?P<branch>\S+)", flat)
    if matched is None:
        return False
    return matched.group("branch") != "undefined"


def _e2e_frontend_offenders() -> tuple[list[str], int]:
    """每个跑 playwright 的 job：测试步骤前必须有进程起在测试端要去的端口上。"""
    offenders: list[str] = []
    if not E2E_WORKFLOW.is_file():
        return [f"检查 19：workflow 文件不存在 {_repo_rel(E2E_WORKFLOW)}"], 0
    if not PLAYWRIGHT_CONFIG.is_file():
        return [f"检查 19：{_repo_rel(PLAYWRIGHT_CONFIG)} 不存在，探针该等哪个端口无从同源"], 0

    port = _playwright_base_url_port(PLAYWRIGHT_CONFIG.read_text(encoding="utf-8"))
    if port is None:
        return ["检查 19：playwright.config.ts 的 baseURL 里读不到端口，等待探针没有核对依据"], 0

    steps = _workflow_steps(E2E_WORKFLOW)
    tested: list[str] = []
    for name, start, end in _workflow_job_ranges(E2E_WORKFLOW):
        job_steps = [s for s in steps if start <= s["lineno"] <= end]
        tests = [s for s in job_steps if _PLAYWRIGHT_TEST_RE.search(s["run"])]
        if not tests:
            continue
        tested.append(name)
        test_step = tests[0]
        before = [s for s in job_steps if s["lineno"] < test_step["lineno"]]
        serve = [s for s in before if _FRONTEND_SERVE_RE.search(s["run"])]
        if not serve:
            offenders.append(
                f"{_repo_rel(E2E_WORKFLOW)}#{name}:「{test_step['name']}」之前没有任何以后台方式起前端"
                f"（`npm run dev … &`）的步骤 ⇒ CI 上 :{port} 没有进程，浏览器用例整批 "
                "net::ERR_CONNECTION_REFUSED（第一百一十一批取证：run 38332373255 里 35 失败/28 通过，"
                "35 条报错全是这一条，而它此前被上一步的 Flyway 红挡着从未被执行）"
            )
            continue
        serve_step = serve[-1]
        install = [s for s in before if _NPM_CI_RE.search(s["run"])]
        if install and serve_step["lineno"] < install[-1]["lineno"]:
            offenders.append(
                f"{_repo_rel(E2E_WORKFLOW)}#{name}: 起前端（:{serve_step['lineno']}）排在装依赖 "
                f"npm ci（:{install[-1]['lineno']}）之前，那时 node_modules 还不存在，vite 起不来"
            )
            continue
        probes = [
            s
            for s in job_steps
            if serve_step["lineno"] < s["lineno"] < test_step["lineno"] and _PROBE_URL_RE.search(s["run"])
        ]
        if not probes:
            offenders.append(
                f"{_repo_rel(E2E_WORKFLOW)}#{name}: 起了前端却没有等待探针就直接跑测试——"
                f"vite 冷启动的几秒里 :{port} 仍是空的，红会以同样的 ERR_CONNECTION_REFUSED 回来"
            )
            continue
        probe = probes[-1]
        seen = sorted(set(_PROBE_URL_RE.findall(probe["run"])))
        if port not in seen:
            offenders.append(
                f"{_repo_rel(E2E_WORKFLOW)}#{name}: 等待探针等的是 {seen}，"
                f"而 playwright.config.ts 的 baseURL 端口是 {port}——两处不同源，改一处就孤儿一处"
            )
        elif "exit 1" not in probe["run"]:
            offenders.append(
                f"{_repo_rel(E2E_WORKFLOW)}#{name}: 等待探针超时后没有 exit 1，"
                "前端起不来也照样往下跑，红会挪到测试步骤里换一种报错呈现"
            )
    if not tested:
        offenders.append(
            "检查 19 的适用面为空：没有任何 job 再调用 `npx playwright test`——"
            f"删步骤或改命令名会让这条门静默变绿（预期 {sorted(E2E_TEST_JOBS)}）"
        )
    elif not E2E_TEST_JOBS <= set(tested):
        offenders.append(
            f"检查 19 的适用面缩小了：现在扫到 {sorted(tested)}，"
            f"少了 {sorted(E2E_TEST_JOBS - set(tested))}——那个 job 里的端口契约没人核了"
        )
    return offenders, len(tested)


def check_e2e_frontend_server() -> None:
    """检查 19：e2e 轨的"测试步骤写了、:3000 上的实体没有"。

    第一百一十一批的取证：第一百零八批把 Flyway 那一步修绿之后，`Run full E2E suite`
    第一次真的被执行，于是暴露出它下面那一层——e2e.yml 两个 job 的步骤序列都是
    `npm ci` → `playwright install` → `npx playwright test`，中间没有一步起前端；
    同时 playwright.config.ts:31-38 在 `CI` 为真时把 `webServer` 置成 `undefined`
    （本地开发靠它起 `npm run dev`），于是 CI 里没有任何进程监听 :3000。
    同 job 的 `Wait for Java backend` / `Wait for Python AI` 两条轮询都绿，
    缺的正是前端那一条。这条门把这个形状钉住：谁起、按什么顺序起、等多久、
    等的端口必须与测试端 baseURL 同源，且 config 不得在 CI 档再自起一次
    （两处各起一半就是 EADDRINUSE）。
    """
    offenders, jobs = _e2e_frontend_offenders()
    if PLAYWRIGHT_CONFIG.is_file() and E2E_WORKFLOW.is_file():
        text = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")
        if _playwright_ci_autostarts(text) and _FRONTEND_SERVE_RE.search(
            "\n".join(s["run"] for s in _workflow_steps(E2E_WORKFLOW))
        ):
            offenders.append(
                "e2e 轨有两个起前端的主人：playwright.config.ts 在 CI 档也自起 webServer，"
                f"而 {_repo_rel(E2E_WORKFLOW)} 里另有显式的 `npm run dev … &` 步骤——"
                f"同一端口抢两次，后起的会 EADDRINUSE。CI 档归工作流管，config 那边必须 undefined"
            )
    if offenders:
        problems.append("e2e 轨的前端服务契约不成立:\n    " + "\n    ".join(offenders))
    else:
        port = _playwright_base_url_port(PLAYWRIGHT_CONFIG.read_text(encoding="utf-8"))
        print(
            f"[ok] e2e 轨前端服务契约：{jobs} 个含 playwright 测试的 job 都在测试步骤之前起了前端，"
            f"并带了超时即红的等待探针，探针端口与 playwright.config.ts 的 baseURL 同为 :{port}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-columns", action="store_true")
    parser.add_argument("--internal-token-keys", action="store_true")
    parser.add_argument("--test-counts", action="store_true")
    parser.add_argument("--flyway-doc-sync", action="store_true")
    parser.add_argument("--h2-schema-drift", action="store_true")
    parser.add_argument("--readme-claims", action="store_true")
    parser.add_argument("--helm-value-roots", action="store_true")
    parser.add_argument("--container-uid", action="store_true")
    parser.add_argument("--document-storage-root", action="store_true")
    parser.add_argument("--eval-harness-storage", action="store_true")
    parser.add_argument("--requirements-markers", action="store_true")
    parser.add_argument("--frontend-time-entry", action="store_true")
    parser.add_argument("--write-clock-caliber", action="store_true")
    parser.add_argument("--python-clock-caliber", action="store_true")
    parser.add_argument("--workflow-run-scalars", action="store_true")
    parser.add_argument("--db-lock-lifetime", action="store_true")
    parser.add_argument("--flyway-cli", action="store_true")
    parser.add_argument("--container-runtime-contract", action="store_true")
    parser.add_argument("--e2e-frontend-server", action="store_true")
    args = parser.parse_args()

    if not (args.tenant_columns or args.internal_token_keys or args.test_counts
            or args.flyway_doc_sync or args.h2_schema_drift
            or args.readme_claims or args.helm_value_roots or args.container_uid
            or args.document_storage_root or args.eval_harness_storage
            or args.requirements_markers or args.frontend_time_entry
            or args.write_clock_caliber or args.python_clock_caliber
            or args.workflow_run_scalars or args.db_lock_lifetime
            or args.flyway_cli or args.container_runtime_contract
            or args.e2e_frontend_server):
        args.tenant_columns = args.internal_token_keys = args.test_counts = \
            args.flyway_doc_sync = args.h2_schema_drift = \
            args.readme_claims = args.helm_value_roots = args.container_uid = \
            args.document_storage_root = args.eval_harness_storage = \
            args.requirements_markers = args.frontend_time_entry = \
            args.write_clock_caliber = args.python_clock_caliber = \
            args.workflow_run_scalars = args.db_lock_lifetime = args.flyway_cli = \
            args.container_runtime_contract = args.e2e_frontend_server = True

    if args.tenant_columns:
        check_tenant_columns()
    if args.internal_token_keys:
        check_internal_token_keys()
    if args.test_counts:
        check_test_counts()
    if args.flyway_doc_sync:
        check_flyway_doc_sync()
    if args.h2_schema_drift:
        check_h2_schema_drift()
    if args.readme_claims:
        check_readme_claims()
    if args.helm_value_roots:
        check_helm_value_roots()
    if args.container_uid:
        check_container_uid_consistency()
    if args.document_storage_root:
        check_document_storage_root_contract()
    if args.eval_harness_storage:
        check_eval_harness_storage()
    if args.requirements_markers:
        check_requirements_platform_markers()
    if args.frontend_time_entry:
        check_frontend_time_entry()
    if args.write_clock_caliber:
        check_write_clock_caliber()
    if args.python_clock_caliber:
        check_python_clock_caliber()
    if args.workflow_run_scalars:
        check_workflow_run_scalars()
    if args.db_lock_lifetime:
        check_db_lock_lifetime()
    if args.flyway_cli:
        check_flyway_cli()
    if args.container_runtime_contract:
        check_container_runtime_contract()
    if args.e2e_frontend_server:
        check_e2e_frontend_server()

    if problems:
        print("\n发现问题:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n静态校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
