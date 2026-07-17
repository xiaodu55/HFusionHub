import pytest

from app.api.runtime import _friendly_provider_error
from app.core.llm.custom_provider import build_user_llm
from app.core.llm.deepseek_llm import DeepSeekLLM
from app.core.llm.ollama_llm import OllamaLLM


def test_builds_openai_compatible_provider_and_accepts_v1_base_url():
    llm = build_user_llm({
        "provider_type": "openai_compatible",
        "provider_name": "Example",
        "base_url": "https://api.example.com/v1/",
        "model": "example-chat",
        "api_key": "secret",
    })
    assert isinstance(llm, DeepSeekLLM)
    assert llm.model == "example-chat"
    assert llm._chat_completions_url() == "https://api.example.com/v1/chat/completions"


def test_builds_ollama_provider_without_api_key():
    llm = build_user_llm({
        "provider_type": "ollama",
        "provider_name": "Local",
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:3b",
    })
    assert isinstance(llm, OllamaLLM)
    assert llm.model == "qwen2.5:3b"


def test_cloud_provider_requires_api_key():
    with pytest.raises(ValueError, match="API Key"):
        build_user_llm({
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com",
            "model": "example-chat",
        })


@pytest.mark.parametrize("base_url", [
    "file:///etc/passwd",
    "http://169.254.169.254",
    "http://metadata.google.internal",
])
def test_rejects_unsafe_base_urls(base_url):
    with pytest.raises(ValueError):
        build_user_llm({
            "provider_type": "ollama",
            "base_url": base_url,
            "model": "test",
        })


@pytest.mark.parametrize(("error", "expected"), [
    ("API request failed (401): Authentication Fails", "API Key 无效"),
    ("API request failed (402): Insufficient Balance", "余额不足"),
    ("API request failed (404): model_not_found", "没有找到该模型"),
    ("All connection attempts failed", "无法连接供应商"),
])
def test_provider_errors_are_user_friendly(error, expected):
    assert expected in _friendly_provider_error(error)
