import httpx
import pytest

from app.core.embedding.ollama import OllamaEmbedding
from app.core.llm.deepseek_llm import DeepSeekLLM


def test_deepseek_error_includes_upstream_message():
    response = httpx.Response(
        400,
        json={
            "error": {
                "message": "supported models are deepseek-v4-pro or deepseek-v4-flash"
            }
        },
        request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
    )

    with pytest.raises(RuntimeError, match="deepseek-v4-flash"):
        DeepSeekLLM._ensure_success(response)


@pytest.mark.asyncio
async def test_ollama_embedding_uses_batch_api_and_requested_dimension(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, timeout):
            captured.update(url=url, payload=json, timeout=timeout)
            return FakeResponse()

    monkeypatch.setattr(
        "app.core.embedding.ollama.httpx.AsyncClient",
        lambda: FakeClient(),
    )

    embedding = OllamaEmbedding(
        base_url="http://localhost:11434/",
        model="qwen3-embedding:8b-fp16",
        dimension=2,
    )
    result = await embedding.generate_batch(["first", "second"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://localhost:11434/api/embed"
    assert captured["payload"] == {
        "model": "qwen3-embedding:8b-fp16",
        "input": ["first", "second"],
        "dimensions": 2,
    }


@pytest.mark.asyncio
async def test_ollama_embedding_rejects_wrong_dimension(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, timeout):
            return FakeResponse()

    monkeypatch.setattr(
        "app.core.embedding.ollama.httpx.AsyncClient",
        lambda: FakeClient(),
    )
    monkeypatch.setenv("EMBEDDING_MAX_RETRIES", "1")

    embedding = OllamaEmbedding(dimension=2)
    with pytest.raises(ValueError, match="expected 2, got 3"):
        await embedding.generate("wrong dimension")
