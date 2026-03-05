"""
Pytest Configuration — 测试配置与隔离 fixture。
"""

import sys
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置 pytest-asyncio
pytest_plugins = ['pytest_asyncio']

# HTTP route tests emulate the Java application service.  Production has no
# fallback token; the test process supplies an explicit, non-secret value.
from app.utils.config import config

config.INTERNAL_API_TOKEN = "test-internal-token"
config.EMBEDDING_ALLOW_FALLBACK = True


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
