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
  python scripts/static-checks.py            # 全部检查
退出码: 0=通过, 1=发现违规
"""

import argparse
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
    args = parser.parse_args()

    if not (args.tenant_columns or args.internal_token_keys or args.test_counts
            or args.flyway_doc_sync or args.h2_schema_drift
            or args.readme_claims or args.helm_value_roots or args.container_uid
            or args.document_storage_root or args.eval_harness_storage
            or args.requirements_markers or args.frontend_time_entry
            or args.write_clock_caliber):
        args.tenant_columns = args.internal_token_keys = args.test_counts = \
            args.flyway_doc_sync = args.h2_schema_drift = \
            args.readme_claims = args.helm_value_roots = args.container_uid = \
            args.document_storage_root = args.eval_harness_storage = \
            args.requirements_markers = args.frontend_time_entry = \
            args.write_clock_caliber = True

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

    if problems:
        print("\n发现问题:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n静态校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
