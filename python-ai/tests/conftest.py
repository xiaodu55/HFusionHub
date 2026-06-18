"""
Pytest Configuration — 测试配置与隔离 fixture。
"""

import os
import sys
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
# 评测基建模块位于 scripts/（运行时包不依赖），测试需可导入
sys.path.insert(0, str(project_root / 'scripts'))

# 配置 pytest-asyncio
pytest_plugins = ['pytest_asyncio']

# ── 测试环境隔离（必须在导入 app.utils.config 之前设置）────────────────
# 本地开发 .env 常为 VECTOR_STORE_MODE=cluster（容器 Milvus），会让一批
# 依赖 lite co-store JSON 语义的测试在本地失败而在 CI（无 .env）通过——
# 测试必须 hermetic：默认强制 lite，需要 cluster 语义的测试自行显式设置。
os.environ["VECTOR_STORE_MODE"] = "lite"
# ModelGateway 现为唯一 LLM 链（旧 FailoverLLM 链已退役）；gateway 读取
# .env 配置的差异由各测试按需 monkeypatch provider，无需全局开关。

# HTTP route tests emulate the Java application service.  Production has no
# fallback token; the test process supplies an explicit, non-secret value.
from app.utils.config import config

config.INTERNAL_API_TOKEN = "test-internal-token"
config.EMBEDDING_ALLOW_FALLBACK = True

# Tests run without a Java backend — use transparent degradation so feature
# flags don't override env-var-based config (preserves existing test behavior).
os.environ.setdefault("FEATURE_FLAG_DEGRADATION", "transparent")


class FakeInternalNoteResponse:
    """httpx.Response 替身 — 模拟 Java /api/internal/notes 成功响应。"""

    status_code = 200
    is_error = False

    def __init__(self, payload=None):
        self._payload = payload or {"code": 200, "data": {"note_id": 101, "title": "测试笔记"}}

    def json(self):
        return self._payload


def mock_java_note_backend():
    """把 write_note 的 Java 持久化调用替换为成功响应。

    返回 ``unittest.mock.patch`` 上下文管理器，pytest 与 unittest 用例通用：

        with mock_java_note_backend():
            result = await tool.execute(...)
    """
    from unittest.mock import AsyncMock, patch

    async def _fake_post(url, **kwargs):
        # patch 类属性后实例调用不会传 self；第一个位置参数是 url
        return FakeInternalNoteResponse()

    return patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_fake_post))

from app.core.tenant.context import set_tenant_id, clear_tenant_id


@pytest.fixture(autouse=True)
def _tenant_context():
    """Give every test a deterministic tenant context (default tenant 1).

    The HTTP middleware normally populates this contextvar; unit tests that
    call the vector store / services directly bypass the middleware, so we seed
    it here.  Tests that need a different tenant set the contextvar explicitly.
    """
    set_tenant_id(1)
    yield
    clear_tenant_id()


# ── Milvus 隔离 fixture ─────────────────────────────────────────────────

@pytest.fixture
def tmp_milvus_db(tmp_path, monkeypatch):
    """隔离的临时 Milvus Lite 数据库 — 不触及开发运行中的 milvus_data.db。

    每个使用此 fixture 的测试都获得独立的临时数据库文件，
    从而避免 ``DataDirLockedError: another process holds the lock``。
    """
    import app.core.vectorstore.milvus_store as ms

    # 保存原始值，用于 tear-down 恢复。
    _orig_client = ms._client
    _orig_ms_path = ms.MILVUS_LITE_PATH
    _orig_cfg_path = config.MILVUS_LITE_PATH

    # 临时数据库路径（tmp_path 是 pytest 管理的临时目录）。
    temp_db = tmp_path / "milvus_test.db"

    # 重定向 Milvus 数据文件 — 同时 patch config 和 milvus_store 的模块级变量。
    monkeypatch.setattr(config, "MILVUS_LITE_PATH", str(temp_db))
    monkeypatch.setattr(ms, "MILVUS_LITE_PATH", temp_db.resolve())
    monkeypatch.setattr(ms, "_client", None)

    # 在临时数据库中初始化 collection。
    ms.create_collection()

    yield temp_db

    # 恢复模块级状态，避免污染后续测试。
    ms._client = _orig_client
    ms.MILVUS_LITE_PATH = _orig_ms_path
    config.MILVUS_LITE_PATH = _orig_cfg_path


# ── Audit SQLite 隔离 fixture ───────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_audit_db(tmp_path):
    """Redirect audit SQLite to a temp dir for every test, then restore."""
    from app.core.plugin import audit as audit_mod
    audit_mod._reset_db(str(tmp_path))
    yield
    audit_mod._reset_db(None)
