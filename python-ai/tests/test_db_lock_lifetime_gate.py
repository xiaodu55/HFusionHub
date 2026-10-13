r"""检查 16 的门禁测试：审计库那个跨线程共享的 SQLite 连接，取用与关闭都必须在 `_db_lock` 内。

第一百零三批在容器里、第一百零四批在本地各踩到一次解释器级崩溃（退出码 139，
`Windows fatal exception: access violation` / `Fatal Python error: Segmentation fault`），
第一百零四批那次拿到了崩溃栈：线程在 `audit.py` 的 `_cleanup_synced` 里对一个已经被
`_reset_db()` 关掉的连接执行 `execute`。形态是 `db = _get_db()` 写在 `with _db_lock:` **之前**
——锁排开了"execute 撞 execute"，排不开"锁外取到的连接对象 vs close()"。

时序判据只能抽中这种窗口（同一命令第一次绿、第二次红），所以这里钉的是**形态**；
行为侧那两条确定性判据在 `tests/test_plugin_audit.py::TestDbConnectionLifetime`。

本文件钉四件事：对真仓库绿、接进了默认全跑档、注入的每种漂移会红、
以及"改名让适用面消失"不会静默变绿。
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "static-checks.py"
AUDIT_MODULE = ROOT / "python-ai" / "app" / "core" / "plugin" / "audit.py"

# 第一百零六批修完之后的现行形态：取连接在锁体内。
GUARDED = """import threading

_db_lock = threading.Lock()
_db_conn = None


def _get_db():
    global _db_conn
    if _db_conn is None:
        _db_conn = object()
    return _db_conn


def write_row(value):
    with _db_lock:
        db = _get_db()
        db.execute(value)
"""

# 崩溃栈对应的形态：引用在 `with` 之前取，之后锁被放掉，别人就有机会关掉它。
GETTER_OUTSIDE_LOCK = GUARDED.replace(
    "    with _db_lock:\n        db = _get_db()",
    "    db = _get_db()\n    with _db_lock:",
)

# `_reset_db` 不持锁就关连接：本批行为判据抓的正是它。
CLOSE_OUTSIDE_LOCK = """import threading

_db_lock = threading.Lock()
_db_conn = None


def _reset_db(new_dir=None):
    global _db_conn
    if _db_conn is not None:
        _db_conn.close()
    _db_conn = None
"""

# 同行写法：表达式确实在锁内求值，不该判红。
SAME_LINE_WITH_BODY = GUARDED.replace(
    "    with _db_lock:\n        db = _get_db()\n        db.execute(value)",
    "    with _db_lock: db = _get_db(); db.execute(value)",
)

# 整组改名：门禁若只认 `_db_lock` 这个名字，这一改就让它扫不到任何文件。
RENAMED_LOCK = GUARDED.replace("_db_lock", "_sql_lock")

# 语法坏掉的模块：报错文字里带着"本检查无法核对"，不能静默跳过。
BROKEN_SOURCE = "_db_conn = None\n\n\ndef broken(:\n    return 1\n"


def _load_checker():
    spec = importlib.util.spec_from_file_location("hfusionhub_static_checks", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(tmp_path: Path, **files: str):
    module = _load_checker()
    app_dir = tmp_path / "app"
    app_dir.mkdir(exist_ok=True)
    for name, body in files.items():
        (app_dir / f"{name}.py").write_text(body, encoding="utf-8")
    module.PYTHON_APP_DIR = app_dir
    module.problems.clear()
    return module


def _offenders(module, source: str) -> tuple[list[str], int]:
    return module._db_lock_shape_offenders(source, "fixture.py")


class TestCheck16OnTheRepo:
    def test_gate_passes_on_the_repo(self):
        module = _load_checker()
        module.problems.clear()
        module.check_db_lock_lifetime()
        assert module.problems == [], module.problems

    def test_gate_is_in_the_default_all_mode(self):
        """并入默认全跑档，否则只在显式传参时生效（第八十三批的接线哑火形态）。"""
        source = CHECKER.read_text(encoding="utf-8")
        main_body = source[source.index("def main()"):]
        assert "--db-lock-lifetime" in main_body
        all_mode = main_body[
            main_body.index("args = parser.parse_args()"):main_body.index("if args.tenant_columns:")
        ]
        assert all_mode.count("args.db_lock_lifetime") >= 2, (
            f"接线只出现一次，全跑档很可能没并进去：{all_mode!r}"
        )
        assert "check_db_lock_lifetime()" in main_body

    def test_the_real_module_counts_enough_references(self):
        """绿不能是"没数到引用"：真模块里至少 10 处取连接、3 处连接读写都要被核对到。"""
        module = _load_checker()
        offenders, checked = _offenders(module, AUDIT_MODULE.read_text(encoding="utf-8"))
        assert offenders == []
        assert checked >= 13, f"只核对到 {checked} 处引用，规则多半没匹配上现行形态"

    def test_the_getter_documents_the_contract(self):
        """门禁管形，不管调用方读不读得懂：取连接的函数自己必须写明"调用方已持锁"。"""
        source = AUDIT_MODULE.read_text(encoding="utf-8")
        assert "调用方必须已经持有" in source, "_get_db 的前置条件又没人写了"


class TestCheck16Drifts:
    def test_guarded_shape_is_clean(self, tmp_path):
        module = _fixture(tmp_path, clean=GUARDED)
        module.check_db_lock_lifetime()
        assert module.problems == []

    def test_getter_called_outside_the_lock_is_red(self, tmp_path):
        module = _fixture(tmp_path, drift=GETTER_OUTSIDE_LOCK)
        module.check_db_lock_lifetime()
        text = "\n".join(module.problems)
        assert "db = _get_db()" in text, module.problems
        assert "drift.py:15" in text, f"红句没点到取连接那一行：{text}"

    def test_closing_the_connection_outside_the_lock_is_red(self, tmp_path):
        """`_reset_db` 是本批崩溃的另一半：它对 `_db_conn` 的读写也必须在锁内。"""
        module = _fixture(tmp_path, drift=CLOSE_OUTSIDE_LOCK)
        module.check_db_lock_lifetime()
        text = "\n".join(module.problems)
        assert "drift.py:9" in text and "_db_conn.close()" in text, module.problems

    def test_same_line_with_body_is_not_an_offender(self, tmp_path):
        """`with _db_lock: db = _get_db()` 的求值确实在锁内，把它判红只会逼人改出更差的写法。"""
        module = _fixture(tmp_path, ok=SAME_LINE_WITH_BODY)
        module.check_db_lock_lifetime()
        assert module.problems == []

    def test_getter_body_itself_is_exempt(self, tmp_path):
        """`_get_db` 本体读写的就是那个全局，它只在锁内被调用——不排除就无解。"""
        offenders, _ = _offenders(_load_checker(), GUARDED)
        assert offenders == []

    def test_renaming_the_lock_does_not_silence_the_gate(self, tmp_path):
        """整组改名后锁名对不上，引用就会全部落在"无保护区间"里 ⇒ 红，而不是空扫描变绿。"""
        module = _fixture(tmp_path, drift=RENAMED_LOCK)
        module.check_db_lock_lifetime()
        assert module.problems, "改名让检查 16 静默通过"

    def test_empty_scope_is_red_not_green(self, tmp_path):
        """app/ 里再没有任何文件碰这三个名字＝适用面消失，必须判红。"""
        module = _fixture(tmp_path, unrelated="VALUE = 1\n")
        module.check_db_lock_lifetime()
        assert any("适用面为空" in p for p in module.problems), module.problems

    def test_unparseable_module_is_reported_not_skipped(self, tmp_path):
        module = _fixture(tmp_path, broken=BROKEN_SOURCE)
        module.check_db_lock_lifetime()
        assert any("解析失败" in p for p in module.problems), module.problems
