"""Safe runtime diagnostics for the AI control plane.

The endpoint deliberately reports operational state only.  It never exposes
provider URLs, API keys, prompts, document content, or any other secret.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter

from app.core.vectorstore.milvus_store import vector_store_status
from app.utils.config import config
from app.utils.feature_flag import feature_flags


router = APIRouter(tags=["runtime"])


def _environment_enabled(name: str, default: bool = False) -> bool:
    """Read a deployment boolean without returning its source value."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def _probe_ollama() -> tuple[bool, set[str]]:
    """Probe the local provider once with a short timeout.

    This keeps the UI honest about local model availability while ensuring an
    unreachable optional Ollama installation cannot delay the page for long.
    Uses httpx.AsyncClient to avoid blocking the FastAPI event loop.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(f"{base_url}/api/tags")
            if response.status_code != 200:
                return False, set()
            models = response.json().get("models", [])
            return True, {
                str(item.get("name", ""))
                for item in models
                if isinstance(item, dict) and item.get("name")
            }
    except Exception:
        return False, set()


def _model_available(configured: str, models: set[str]) -> bool:
    """Allow exact model names and the common tag-less form."""
    if configured in models:
        return True
    return any(model.split(":", 1)[0] == configured.split(":", 1)[0] for model in models)


async def _status_payload() -> dict[str, Any]:
    ollama_reachable, ollama_models = await _probe_ollama()
    ollama_chat_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
    ollama_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b-fp16")
    deepseek_configured = bool(config.DEEPSEEK_API_KEY)
    mock_enabled = _environment_enabled("LLM_ALLOW_MOCK")

    ollama_chat_ready = ollama_reachable and _model_available(ollama_chat_model, ollama_models)
    ollama_embedding_ready = ollama_reachable and _model_available(ollama_embedding_model, ollama_models)

    if deepseek_configured:
        llm = {
            "provider": "deepseek",
            "provider_label": "DeepSeek",
            "model": config.DEEPSEEK_MODEL,
            "state": "configured",
            "detail": "已配置远程对话模型；密钥不会在此处显示。",
        }
    elif ollama_chat_ready:
        llm = {
            "provider": "ollama",
            "provider_label": "Ollama",
            "model": ollama_chat_model,
            "state": "ready",
            "detail": "本地对话模型已检测到。",
        }
    elif mock_enabled:
        llm = {
            "provider": "mock",
            "provider_label": "Mock",
            "model": "mock",
            "state": "development",
            "detail": "当前使用开发测试模型，不适合生产回答。",
        }
    else:
        llm = {
            "provider": None,
            "provider_label": "未配置",
            "model": None,
            "state": "unavailable",
            "detail": "未检测到可用的对话模型配置。",
        }

    if ollama_embedding_ready:
        embedding = {
            "provider": "ollama",
            "provider_label": "Ollama",
            "model": ollama_embedding_model,
            "dimension": config.EMBEDDING_DIMENSION,
            "state": "ready",
            "detail": "本地 Embedding 模型已检测到，可用于文档索引。",
        }
    elif config.EMBEDDING_ALLOW_FALLBACK:
        embedding = {
            "provider": "test_fallback",
            "provider_label": "测试降级",
            "model": None,
            "dimension": config.EMBEDDING_DIMENSION,
            "state": "development",
            "detail": "正在使用随机向量降级，仅适用于测试，不能保证检索质量。",
        }
    else:
        embedding = {
            "provider": None,
            "provider_label": "未就绪",
            "model": ollama_embedding_model,
            "dimension": config.EMBEDDING_DIMENSION,
            "state": "unavailable",
            "detail": "未检测到可用的 Embedding 模型；新文档无法可靠建立索引。",
        }

    try:
        vector_store = vector_store_status()
    except Exception:
        vector_store = {"ready": False, "collection": None, "error": "向量库状态检查失败"}

    llm_ready = llm["state"] in {"configured", "ready"}
    status = "ready" if llm_ready and embedding["state"] == "ready" and vector_store.get("ready") else "degraded"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llm": llm,
        "embedding": embedding,
        "vector_store": {
            "ready": bool(vector_store.get("ready")),
            "collection": vector_store.get("collection"),
            "collection_exists": vector_store.get("collection_exists"),
            "detail": vector_store.get("error") or (
                "向量库已就绪" if vector_store.get("ready") else "向量库不可用"
            ),
        },
        "providers": [
            {
                "id": "deepseek",
                "label": "DeepSeek",
                "purpose": "对话模型",
                "configured": deepseek_configured,
                "state": "configured" if deepseek_configured else "not_configured",
            },
            {
                "id": "ollama_chat",
                "label": "Ollama 对话模型",
                "purpose": "对话模型",
                "model": ollama_chat_model,
                "configured": bool(os.getenv("OLLAMA_BASE_URL")),
                "reachable": ollama_reachable,
                "model_available": ollama_chat_ready,
                "state": "ready" if ollama_chat_ready else ("reachable" if ollama_reachable else "unavailable"),
            },
            {
                "id": "ollama_embedding",
                "label": "Ollama Embedding",
                "purpose": "文档向量化",
                "model": ollama_embedding_model,
                "configured": bool(os.getenv("OLLAMA_BASE_URL")),
                "reachable": ollama_reachable,
                "model_available": ollama_embedding_ready,
                "state": "ready" if ollama_embedding_ready else ("reachable" if ollama_reachable else "unavailable"),
            },
        ],
        "features": {
            "hybrid_retrieval": config.RAG_HYBRID_ENABLED,
            "graph_retrieval": config.RAG_GRAPH_ENABLED and feature_flags.is_enabled("rag.graph.enabled"),
            "reranker": config.RAG_RERANKER_MODE if feature_flags.is_enabled("rag.reranker.enabled") else "disabled",
            "agent_workflow": config.RAG_AGENT_WORKFLOW_ENABLED and feature_flags.is_enabled("agent.enabled"),
            "multi_agent": config.RAG_MULTI_AGENT_ENABLED and feature_flags.is_enabled("agent.multi_agent.enabled"),
            "write_tools": feature_flags.is_enabled("agent.write_tools.enabled"),
            "web_search": feature_flags.is_enabled("agent.web_search.enabled"),
            "approval_required": feature_flags.is_enabled("approval.required_for_write"),
        },
    }


@router.get("/api/runtime/overview")
async def runtime_overview() -> dict[str, Any]:
    """Return the current safe AI runtime snapshot for authenticated operators."""
    return await _status_payload()
