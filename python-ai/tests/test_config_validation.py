"""Config fail-fast validation tests (app.utils.config._validate_config)."""

import pytest

import app.utils.config as config_module
from app.utils.config import config


@pytest.fixture(autouse=True)
def _restore_config():
    """每个用例后恢复 config 单例，避免串扰其它测试。"""
    yield
    config.SERVER_ENV = "development"
    config.VECTOR_STORE_MODE = "lite"
    config.INTERNAL_API_TOKEN = ""
    config.MILVUS_HOST = "localhost"


def _call() -> None:
    config_module._validate_config()


def test_production_requires_internal_token():
    config.SERVER_ENV = "production"
    config.VECTOR_STORE_MODE = "cluster"
    config.INTERNAL_API_TOKEN = ""
    with pytest.raises(RuntimeError, match="PYTHON_AI_INTERNAL_TOKEN"):
        _call()


def test_production_requires_cluster_vector_mode():
    config.SERVER_ENV = "production"
    config.VECTOR_STORE_MODE = "lite"
    config.INTERNAL_API_TOKEN = "secret"
    with pytest.raises(RuntimeError, match="VECTOR_STORE_MODE"):
        _call()


def test_production_cluster_requires_remote_milvus_host():
    config.SERVER_ENV = "production"
    config.VECTOR_STORE_MODE = "cluster"
    config.INTERNAL_API_TOKEN = "secret"
    config.MILVUS_HOST = "localhost"
    with pytest.raises(RuntimeError, match="MILVUS_HOST"):
        _call()


def test_production_cluster_blank_milvus_host_fails_closed():
    config.SERVER_ENV = "production"
    config.VECTOR_STORE_MODE = "cluster"
    config.INTERNAL_API_TOKEN = "secret"
    config.MILVUS_HOST = "  "
    with pytest.raises(RuntimeError, match="MILVUS_HOST"):
        _call()


def test_production_cluster_with_remote_host_passes():
    config.SERVER_ENV = "production"
    config.VECTOR_STORE_MODE = "cluster"
    config.INTERNAL_API_TOKEN = "secret"
    config.MILVUS_HOST = "milvus.internal"
    _call()  # 不应抛异常


def test_development_is_lenient():
    config.SERVER_ENV = "development"
    config.VECTOR_STORE_MODE = "lite"
    config.INTERNAL_API_TOKEN = ""
    config.MILVUS_HOST = "localhost"
    _call()  # 不应抛异常
