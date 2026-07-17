"""Factory selection and production fail-closed behaviour for vector stores."""
import pytest

from app.core.vectorstore.factory import get_vector_store, reset_vector_store
from app.core.vectorstore.milvus_cluster import MilvusClusterStore
from app.core.vectorstore.milvus_lite import MilvusLiteStore


@pytest.fixture(autouse=True)
def _reset_store():
    reset_vector_store()
    yield
    reset_vector_store()


def _set_mode(monkeypatch, mode: str, env: str = "development"):
    monkeypatch.setattr("app.core.vectorstore.factory.config.VECTOR_STORE_MODE", mode)
    monkeypatch.setattr("app.core.vectorstore.factory.config.SERVER_ENV", env)


def test_dev_defaults_to_lite(monkeypatch):
    _set_mode(monkeypatch, "lite", "development")
    store = get_vector_store()
    assert isinstance(store, MilvusLiteStore)


def test_dev_allows_cluster(monkeypatch):
    _set_mode(monkeypatch, "cluster", "development")
    store = get_vector_store()
    assert isinstance(store, MilvusClusterStore)


def test_production_lite_is_fail_closed(monkeypatch):
    """production + lite must abort instead of initialising a Lite store."""
    _set_mode(monkeypatch, "lite", "production")
    with pytest.raises(SystemExit):
        get_vector_store()


def test_staging_lite_is_fail_closed(monkeypatch):
    _set_mode(monkeypatch, "lite", "staging")
    with pytest.raises(SystemExit):
        get_vector_store()


def test_production_cluster_is_allowed(monkeypatch):
    _set_mode(monkeypatch, "cluster", "production")
    store = get_vector_store()
    assert isinstance(store, MilvusClusterStore)


def test_invalid_mode_raises(monkeypatch):
    _set_mode(monkeypatch, "bogus", "development")
    with pytest.raises(SystemExit):
        get_vector_store()
