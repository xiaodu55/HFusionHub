"""
LLM (Large Language Model) Integration Module
Supports DeepSeek API (primary), Ollama local models (fallback), and Mock (testing)
"""

import os
from .base import BaseLLM, ChatMessage, LLMResponse
from .deepseek_llm import DeepSeekLLM
from .ollama_llm import OllamaLLM
from .mock_llm import MockLLM

__all__ = ['BaseLLM', 'ChatMessage', 'LLMResponse', 'DeepSeekLLM', 'OllamaLLM', 'MockLLM', 'get_llm']


def get_llm(model: str = None) -> BaseLLM:
    """
    Get LLM instance with fallback strategy

    Priority:
    1. DeepSeek API (primary)
    2. Ollama (local fallback)
    3. Mock LLM (testing fallback)
    """
    from app.utils.config import config

    # 1. Try DeepSeek API first (primary)
    deepseek_api_key = config.DEEPSEEK_API_KEY
    deepseek_base_url = config.DEEPSEEK_BASE_URL

    if deepseek_api_key:
        try:
            llm = DeepSeekLLM(
                api_key=deepseek_api_key,
                base_url=deepseek_base_url,
                model=model or config.DEEPSEEK_MODEL
            )
            # Test availability with a simple request
            if llm.is_available():
                return llm
        except Exception as e:
            print(f"[LLM] DeepSeek API failed: {e}, trying Ollama...")

    # 2. Try Ollama local models (fallback)
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        import httpx
        response = httpx.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            llm = OllamaLLM(
                base_url=ollama_url,
                model=model or "qwen2.5:latest"
            )
            return llm
    except Exception as e:
        print(f"[LLM] Ollama failed: {e}, using Mock LLM...")

    # 3. Fallback to Mock LLM (testing)
    return MockLLM()
