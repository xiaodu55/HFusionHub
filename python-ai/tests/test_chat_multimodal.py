"""对话图片输入（实验特性 CHAT_MULTIMODAL_INPUT_ENABLED）测试。

覆盖：data URL 校验规则、flag 门控、上下文组装（含单图失败兜底）、
/api/chat/stream 端点的 400 与增强 query 组装。
"""

import base64

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.utils import vision

VALID_PNG = "data:image/png;base64," + base64.b64encode(
    b"\x89PNG\r\n\x1a\nfake-png-payload"
).decode()


def _client():
    from app.utils.config import config

    app = create_app()
    return TestClient(
        app,
        headers={
            "X-Internal-Token": config.INTERNAL_API_TOKEN,
            "X-Tenant-Id": "1",
        },
    )


def _enable(monkeypatch, value=True):
    from app.utils.config import config

    monkeypatch.setattr(config, "CHAT_MULTIMODAL_INPUT_ENABLED", value)


# ── validate_data_urls ──────────────────────────────────────────────────


def test_validate_accepts_valid_png():
    assert vision.validate_data_urls([VALID_PNG]) != []


def test_validate_rejects_more_than_four_images():
    with pytest.raises(ValueError, match="最多"):
        vision.validate_data_urls([VALID_PNG] * 5)


def test_validate_rejects_non_image_prefix():
    with pytest.raises(ValueError, match="JPG"):
        vision.validate_data_urls(["data:text/plain;base64,aGVsbG8="])


def test_validate_rejects_broken_base64():
    with pytest.raises(ValueError, match="无法解析"):
        vision.validate_data_urls(["data:image/png;base64,@@@not-base64@@@"])


def test_validate_rejects_oversized_image():
    huge = "data:image/png;base64," + base64.b64encode(b"\x89PNG" + b"0" * (6 * 1024 * 1024)).decode()
    with pytest.raises(ValueError, match="5MB"):
        vision.validate_data_urls([huge])


# ── build_image_context ─────────────────────────────────────────────────


def test_context_raises_when_disabled(monkeypatch):
    _enable(monkeypatch, False)
    with pytest.raises(RuntimeError, match="CHAT_MULTIMODAL_INPUT_ENABLED"):
        vision.build_image_context([VALID_PNG])


def test_context_formats_captions(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(
        vision, "_describe_one", lambda b64: "一张测试图片"
    )
    context = vision.build_image_context([VALID_PNG, VALID_PNG])
    assert "[用户在本次消息中附带了 2 张图片" in context
    assert "图片 1：一张测试图片" in context
    assert "图片 2：一张测试图片" in context
    assert context.endswith("[图片内容结束]")


def test_context_survives_single_image_failure(monkeypatch):
    _enable(monkeypatch)

    def flaky(b64):
        raise RuntimeError("boom")

    monkeypatch.setattr(vision, "_describe_one", flaky)
    context = vision.build_image_context([VALID_PNG])
    assert "（内容未能解析）" in context


# ── /api/chat/stream 端点行为 ───────────────────────────────────────────


@pytest.fixture
def mock_agent_query(monkeypatch):
    """替换 agent 工厂并捕获传给 run_stream 的 query。"""
    captured = {"query": None}

    class _MockAgent:
        async def run_stream(self, **kwargs):
            captured["query"] = kwargs.get("query")
            yield "data: ok"

    monkeypatch.setattr("app.api.chat.get_agent", lambda **kw: _MockAgent())
    return captured


def test_stream_images_rejected_with_friendly_400_when_disabled(monkeypatch):
    _enable(monkeypatch, False)
    client = _client()

    response = client.post(
        "/api/chat/stream",
        json={"message": "这张图里是什么？", "images": [VALID_PNG]},
    )

    assert response.status_code == 400
    assert "图片输入" in response.json()["message"]


def test_stream_rejects_invalid_image_with_400(monkeypatch):
    _enable(monkeypatch)
    client = _client()

    response = client.post(
        "/api/chat/stream",
        json={"message": "看图", "images": ["data:text/html;base64,PGI+"]},
    )

    assert response.status_code == 400
    assert "JPG" in response.json()["message"]


def test_stream_composes_image_context_into_query(monkeypatch, mock_agent_query):
    _enable(monkeypatch)

    def fake_build(data_urls):
        assert data_urls == [VALID_PNG]
        return "[用户在本次消息中附带了 1 张图片，内容如下]\n图片 1：测试\n[图片内容结束]"

    monkeypatch.setattr(vision, "build_image_context", fake_build)
    client = _client()

    response = client.post(
        "/api/chat/stream",
        json={"message": "这张图里是什么？", "images": [VALID_PNG]},
    )

    assert response.status_code == 200
    assert "data: ok" in response.text
    assert mock_agent_query["query"].startswith("[用户在本次消息中附带了 1 张图片")
    assert mock_agent_query["query"].endswith("这张图里是什么？")


def test_stream_without_images_keeps_original_query(monkeypatch, mock_agent_query):
    _enable(monkeypatch)
    client = _client()

    response = client.post("/api/chat/stream", json={"message": "纯文本提问"})

    assert response.status_code == 200
    assert mock_agent_query["query"] == "纯文本提问"
