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

用法:
  python scripts/static-checks.py --tenant-columns
  python scripts/static-checks.py --internal-token-keys
  python scripts/static-checks.py --test-counts
  python scripts/static-checks.py --flyway-doc-sync
  python scripts/static-checks.py --h2-schema-drift
  python scripts/static-checks.py --readme-claims
  python scripts/static-checks.py --helm-value-roots
  python scripts/static-checks.py --container-uid
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
    args = parser.parse_args()

    if not (args.tenant_columns or args.internal_token_keys or args.test_counts
            or args.flyway_doc_sync or args.h2_schema_drift
            or args.readme_claims or args.helm_value_roots or args.container_uid):
        args.tenant_columns = args.internal_token_keys = args.test_counts = \
            args.flyway_doc_sync = args.h2_schema_drift = \
            args.readme_claims = args.helm_value_roots = args.container_uid = True

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

    if problems:
        print("\n发现问题:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n静态校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
