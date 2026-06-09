"""
Configuration management for HFusionHub Python AI Engine
"""

import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration"""

    # DeepSeek API
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    # Optional OpenAI-compatible backup provider (B2: model failover routing).
    # When configured, it joins the FailoverLLM chain after DeepSeek/Ollama.
    OPENAI_COMPATIBLE_API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
    OPENAI_COMPATIBLE_BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "")
    OPENAI_COMPATIBLE_MODEL = os.getenv("OPENAI_COMPATIBLE_MODEL", "")

    # Milvus
    MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
    MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "hfusionhub_chunks")
    MILVUS_USER = os.getenv("MILVUS_USER", "root")
    # 空 = 不启用认证（Milvus 默认无鉴权）；启用 MILVUS_AUTH_ENABLED=true 后需配置
    MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "")
    MILVUS_LITE_PATH = os.getenv("MILVUS_LITE_PATH", "./milvus_data.db")

    # Vector store mode: "lite" (single-process embedded) or "cluster" (remote Milvus).
    # Production / staging environments MUST use "cluster".
    VECTOR_STORE_MODE = os.getenv("VECTOR_STORE_MODE", "lite")

    # Environment name — controls hard safety gates (e.g. vector store mode).
    SERVER_ENV = os.getenv("SERVER_ENV", "development")

    # Server Configuration
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "9000"))
    SERVER_DEBUG = os.getenv("SERVER_DEBUG", "false").lower() == "true"
    # Comma-separated browser origins. Use "*" only for public, credential-free APIs.
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    # File Storage
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

    # Java Backend
    JAVA_BACKEND_URL = os.getenv("JAVA_BACKEND_URL", "http://localhost:8080")

    # Ollama remains an optional local/fallback provider. Keep its endpoint in
    # the same typed configuration boundary as the model name so callers do
    # not read environment variables directly.
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")

    # Required shared secret for Java -> Python requests.  Do not provide a
    # development default: an accidentally exposed worker must fail closed.
    INTERNAL_API_TOKEN = os.getenv("PYTHON_AI_INTERNAL_TOKEN", "")

    # Java owns uploaded files.  The worker may only parse a real file below
    # this mounted/shared directory, never an arbitrary readable host path.
    DOCUMENT_STORAGE_ROOT = os.getenv(
        "DOCUMENT_STORAGE_ROOT", "../java-backend/uploads/documents"
    )

    # Chunking Configuration
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))  # characters
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))  # characters

    # Embedding Configuration
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "unknown")
    EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    EMBEDDING_RETRY_DELAY = float(os.getenv("EMBEDDING_RETRY_DELAY", "1.0"))
    # Allow random-vector fallback ONLY in test environments.  Production must
    # fail-closed when every real embedding provider is unavailable.
    EMBEDDING_ALLOW_FALLBACK = os.getenv("EMBEDDING_ALLOW_FALLBACK", "false").lower() == "true"

    # LLM HTTP client (P3): shared connection pool + bounded retry/backoff.
    # timeout = per-request upstream timeout; max_retries = additional attempts
    # after the first call; retry_backoff = base seconds for exponential backoff
    # (doubles per attempt, plus jitter).
    LLM_HTTP_TIMEOUT_SECONDS = float(os.getenv("LLM_HTTP_TIMEOUT_SECONDS", "120"))
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
    LLM_RETRY_BACKOFF_SECONDS = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "0.5"))

    # Non-streaming LLM response cache (P2): exact-match on
    # (model, temperature, max_tokens, normalized messages) reuses the answer
    # within the TTL so repeated FAQ-style queries do not re-bill every time.
    # Set to 0 to disable (never caches).
    LLM_RESPONSE_CACHE_TTL_SECONDS = float(
        os.getenv("LLM_RESPONSE_CACHE_TTL_SECONDS", "300")
    )

    # Hybrid retrieval configuration.  RRF combines ranks rather than the
    # incomparable raw scores returned by vector and keyword search.
    RAG_HYBRID_ENABLED = os.getenv("RAG_HYBRID_ENABLED", "true").lower() == "true"
    RAG_RRF_K = int(os.getenv("RAG_RRF_K", "60"))
    RAG_RETRIEVAL_CANDIDATE_MULTIPLIER = int(
        os.getenv("RAG_RETRIEVAL_CANDIDATE_MULTIPLIER", "3")
    )
    RAG_RETRIEVAL_MAX_CANDIDATES = int(
        os.getenv("RAG_RETRIEVAL_MAX_CANDIDATES", "30")
    )
    RAG_MIN_EVIDENCE_SCORE = float(os.getenv("RAG_MIN_EVIDENCE_SCORE", "0.35"))

    # Graph retrieval is opt-in.  The GraphRAG channel only reads the scoped
    # graph index whose nodes and edges are backed by chunks in this KB.
    RAG_GRAPH_ENABLED = os.getenv("RAG_GRAPH_ENABLED", "false").lower() == "true"
    RAG_GRAPH_INDEX_PATH = os.getenv("RAG_GRAPH_INDEX_PATH", "./data/rag_scoped_graph.json")

    # Evaluation summaries survive AI-service restarts.  The store never
    # persists benchmark queries or chunk content, only aggregate metrics and
    # case identifiers for failed examples.
    RAG_EVALUATION_DB_PATH = os.getenv(
        "RAG_EVALUATION_DB_PATH", "./data/rag_evaluation_runs.db"
    )

    # Second-stage reranking is opt-in. ``lexical`` is a deterministic local
    # baseline; ``cross_encoder`` needs sentence-transformers and an explicitly
    # configured model name.
    RAG_RERANKER_MODE = os.getenv("RAG_RERANKER_MODE", "lexical")
    RAG_RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-reranker-base")
    RAG_RERANK_CANDIDATE_COUNT = int(os.getenv("RAG_RERANK_CANDIDATE_COUNT", "20"))

    # P8 multimodal evidence is opt-in.  OCR output is converted to regular
    # source-backed chunks, therefore it retains all existing KB scope,
    # citation, deletion and trace behaviour.  A missing binary or optional
    # package only skips enrichment; text/table indexing still completes.
    RAG_MULTIMODAL_ENABLED = os.getenv("RAG_MULTIMODAL_ENABLED", "false").lower() == "true"
    RAG_MULTIMODAL_OCR_ENABLED = os.getenv("RAG_MULTIMODAL_OCR_ENABLED", "false").lower() == "true"
    RAG_MULTIMODAL_OCR_COMMAND = os.getenv("RAG_MULTIMODAL_OCR_COMMAND", "tesseract")
    RAG_MULTIMODAL_OCR_LANGUAGE = os.getenv("RAG_MULTIMODAL_OCR_LANGUAGE", "eng")
    RAG_MULTIMODAL_MAX_IMAGES_PER_DOCUMENT = int(
        os.getenv("RAG_MULTIMODAL_MAX_IMAGES_PER_DOCUMENT", "20")
    )
    RAG_MULTIMODAL_MAX_IMAGE_BYTES = int(
        os.getenv("RAG_MULTIMODAL_MAX_IMAGE_BYTES", str(10 * 1024 * 1024))
    )
    RAG_MULTIMODAL_MAX_OCR_CHARACTERS = int(
        os.getenv("RAG_MULTIMODAL_MAX_OCR_CHARACTERS", "3000")
    )
    RAG_MULTIMODAL_OCR_TIMEOUT_SECONDS = int(
        os.getenv("RAG_MULTIMODAL_OCR_TIMEOUT_SECONDS", "20")
    )

    # P9 is an explicit rollout switch for the bounded single-agent runtime.
    # It wraps the existing read-only React agent; it does not add write tools.
    RAG_AGENT_WORKFLOW_ENABLED = os.getenv("RAG_AGENT_WORKFLOW_ENABLED", "false").lower() == "true"
    RAG_AGENT_TIMEOUT_SECONDS = float(os.getenv("RAG_AGENT_TIMEOUT_SECONDS", "45"))
    RAG_AGENT_MAX_RETRIES = int(os.getenv("RAG_AGENT_MAX_RETRIES", "1"))
    RAG_AGENT_RETRY_DELAY_SECONDS = float(os.getenv("RAG_AGENT_RETRY_DELAY_SECONDS", "0.2"))
    RAG_AGENT_MAX_STEPS = int(os.getenv("RAG_AGENT_MAX_STEPS", "5"))
    RAG_AGENT_TOOL_TIMEOUT_SECONDS = float(os.getenv("RAG_AGENT_TOOL_TIMEOUT_SECONDS", "10"))
    RAG_AGENT_MAX_SEARCH_RESULTS = int(os.getenv("RAG_AGENT_MAX_SEARCH_RESULTS", "5"))
    # Agent V1 whitelist — only knowledge-base research tools.
    # Additional tools (calculate, get_current_time, web_search) may be
    # added via this env var for non-V1 workflows, but the V1
    # WorkflowRuntime hard-enforces the V1 whitelist regardless.
    RAG_AGENT_ALLOWED_TOOLS = tuple(
        item.strip() for item in os.getenv(
            "RAG_AGENT_ALLOWED_TOOLS",
            "search_knowledge_base,read_chunk,list_document_chunks",
        ).split(",") if item.strip()
    )

    # P10 collaboration remains disabled unless P9 is already enabled.  It is
    # an evidence-review wrapper around the bounded, read-only workflow, not a
    # route to autonomous or cross-knowledge-base tool calls.
    RAG_MULTI_AGENT_ENABLED = os.getenv("RAG_MULTI_AGENT_ENABLED", "false").lower() == "true"
    RAG_MULTI_AGENT_TIMEOUT_SECONDS = float(
        os.getenv("RAG_MULTI_AGENT_TIMEOUT_SECONDS", "60")
    )

    # Content safety guardrails.  These env vars are the deployment
    # kill-switches; the effective behaviour is additionally gated by the
    # Java-managed feature flags (guardrails.*) evaluated in
    # app.core.policy.guardrails.  Both must be on for a component to run.
    GUARDRAILS_ENABLED = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    GUARDRAILS_PROMPT_INJECTION_ENABLED = os.getenv(
        "GUARDRAILS_PROMPT_INJECTION_ENABLED", "true"
    ).lower() == "true"
    GUARDRAILS_CONTENT_MODERATION_ENABLED = os.getenv(
        "GUARDRAILS_CONTENT_MODERATION_ENABLED", "true"
    ).lower() == "true"
    GUARDRAILS_PII_MASKING_ENABLED = os.getenv(
        "GUARDRAILS_PII_MASKING_ENABLED", "true"
    ).lower() == "true"


config = Config()


def _validate_config() -> None:
    """Fail fast on unsafe configuration in production / staging.

    Development and tests are deliberately lenient (many tests build the
    config without secrets), but a worker deployed to production/staging must
    fail closed rather than silently serve with a missing internal token or a
    vector-store mode that is only meant for single-process local runs.

    Cluster-mode Milvus connectivity settings are validated the same way:
    a prod worker pointing at ``localhost`` or with a blank host would
    otherwise degrade silently into vector-query failures at request time.
    """
    if config.SERVER_ENV not in ("production", "staging"):
        # Dev/test: still surface a missing internal token so a misconfigured
        # local worker fails loudly (Java proxy gets 401s otherwise) instead of
        # silently degrading — but never hard-fail, tests need leniency.
        if not config.INTERNAL_API_TOKEN:
            logging.getLogger(__name__).warning(
                "PYTHON_AI_INTERNAL_TOKEN is not set; Java -> Python requests "
                "will be rejected (401) until it matches the Java backend."
            )
        return
    if not config.INTERNAL_API_TOKEN:
        raise RuntimeError(
            "PYTHON_AI_INTERNAL_TOKEN is required in production/staging; refusing to start."
        )
    if config.VECTOR_STORE_MODE != "cluster":
        raise RuntimeError(
            "VECTOR_STORE_MODE must be 'cluster' in production/staging; "
            "'lite' is single-process only."
        )
    if config.VECTOR_STORE_MODE == "cluster" and (
        not config.MILVUS_HOST or config.MILVUS_HOST.strip() == ""
        or config.MILVUS_HOST in ("localhost", "127.0.0.1")
    ):
        raise RuntimeError(
            "MILVUS_HOST must point to the remote Milvus in production/staging; "
            f"got {config.MILVUS_HOST!r}. A worker must not silently fall back "
            "to a local vector store."
        )


_validate_config()


def _warn_deprecated_ollama_model() -> None:
    """OLLAMA_MODEL 已废弃用于嵌入 — 嵌入模型统一走 OLLAMA_EMBEDDING_MODEL。

    该变量现仅影响 Ollama 对话兜底供应商的默认模型名（llm/__init__.py），
    设置了它的部署容易误以为它仍控制嵌入。启动时提示一次，辅助迁移。
    """
    if os.getenv("OLLAMA_MODEL"):
        logging.getLogger(__name__).warning(
            "OLLAMA_MODEL is set but deprecated for embeddings — Ollama embeddings use "
            "OLLAMA_EMBEDDING_MODEL instead. OLLAMA_MODEL now only affects the Ollama "
            "chat fallback provider (default model name)."
        )


_warn_deprecated_ollama_model()
