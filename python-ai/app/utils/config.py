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
    # When configured, it joins the provider chain after DeepSeek/Ollama.
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
    # Ollama embedding model — the deprecated OLLAMA_MODEL must not be used here.
    OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b-fp16")

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
    # 空 = 未显式配置；消费端回退 OLLAMA_EMBEDDING_MODEL。
    # 旧默认 "unknown" 会作为 embeddingModel 元数据写入索引，误导排障
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    EMBEDDING_RETRY_DELAY = float(os.getenv("EMBEDDING_RETRY_DELAY", "1.0"))
    # Allow random-vector fallback ONLY in test environments.  Production must
    # fail-closed when every real embedding provider is unavailable.
    EMBEDDING_ALLOW_FALLBACK = os.getenv("EMBEDDING_ALLOW_FALLBACK", "false").lower() == "true"
    # 查询向量缓存（R16-5）：LRU + TTL，只缓存检索侧 query embedding（文档
    # 分块向量文本唯一、无复用价值，不入缓存防挤占查询热点）。TTL=0 禁用
    # （对齐 LLM_RESPONSE_CACHE_TTL_SECONDS 约定）。
    EMBEDDING_QUERY_CACHE_TTL_SECONDS = float(os.getenv("EMBEDDING_QUERY_CACHE_TTL_SECONDS", "600"))
    EMBEDDING_QUERY_CACHE_MAX_ENTRIES = int(os.getenv("EMBEDDING_QUERY_CACHE_MAX_ENTRIES", "256"))
    # 文档索引批量嵌入（R16-7）：单批大小与批间并发。Ollama /api/embed 请求
    # 超时 60s——CPU 推理下过大批次会整批超时，默认 32×并发 2；GPU 部署可
    # 调大批次。并发>1 在 OLLAMA_NUM_PARALLEL=1 时仅重叠 HTTP 开销，无害。
    EMBEDDING_DOC_BATCH_SIZE = int(os.getenv("EMBEDDING_DOC_BATCH_SIZE", "32"))
    EMBEDDING_DOC_BATCH_CONCURRENCY = int(os.getenv("EMBEDDING_DOC_BATCH_CONCURRENCY", "2"))

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
    # Fuzzy (normalized) secondary lookup for the response cache: on an exact
    # miss, retry with whitespace-collapsed / casefolded message text so
    # trivially identical prompts hit the same entry.
    LLM_RESPONSE_CACHE_FUZZY_ENABLED = os.getenv(
        "LLM_RESPONSE_CACHE_FUZZY_ENABLED", "true"
    ).lower() == "true"

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

    # ── 评估中枢（eval_harness）──
    # EVAL_BASE_URL：评估 runner 自调用的生产链路地址（默认本服务）
    EVAL_BASE_URL = os.getenv("EVAL_BASE_URL", "http://localhost:9000")
    # 评审模型：空 = 网关默认主模型；可覆盖（会过 judge_gate 私有部署门禁）
    EVAL_JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "")
    # 评审重复次数（>1 取均值抑制判分方差，成本线性增加）
    EVAL_JUDGE_RUNS = int(os.getenv("EVAL_JUDGE_RUNS", "1"))
    # 评估并发（对生产链路的同时请求数）
    EVAL_CONCURRENCY = int(os.getenv("EVAL_CONCURRENCY", "4"))
    # 单样本调用超时（秒）
    EVAL_TIMEOUT_S = int(os.getenv("EVAL_TIMEOUT_S", "180"))
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
    # P8 vision-LLM 路线（2026-08-29）：用 Ollama 视觉模型生成图片描述，
    # 与 OCR 同一管道（普通文本块 + multimodal metadata），零改动进入检索。
    # VLM 优先、OCR 兜底；模型未拉取/调用失败只跳过增强，永不阻断索引。
    RAG_MULTIMODAL_VLM_ENABLED = os.getenv("RAG_MULTIMODAL_VLM_ENABLED", "false").lower() == "true"
    RAG_MULTIMODAL_VLM_MODEL = os.getenv("RAG_MULTIMODAL_VLM_MODEL", "qwen2.5vl:3b")
    RAG_MULTIMODAL_VLM_BASE_URL = os.getenv("RAG_MULTIMODAL_VLM_BASE_URL", "")
    RAG_MULTIMODAL_VLM_TIMEOUT_SECONDS = int(
        os.getenv("RAG_MULTIMODAL_VLM_TIMEOUT_SECONDS", "180")
    )

    # 对话图片输入（实验档，默认关）：开启后 /api/chat/stream 的消息可携带
    # 图片 data URL，经 Ollama 视觉模型转中文描述后并入提问上下文。
    CHAT_MULTIMODAL_INPUT_ENABLED = os.getenv(
        "CHAT_MULTIMODAL_INPUT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # 知识库 QA 对生成（实验档，默认关）：文档解析入库时用对话 LLM 从分块
    # 生成问答对并并入索引，提升"用户问法≠原文表述"场景的召回率。
    RAG_QA_GENERATION_ENABLED = os.getenv("RAG_QA_GENERATION_ENABLED", "false").lower() in ("1", "true", "yes")
    RAG_QA_MAX_PER_DOC = int(os.getenv("RAG_QA_MAX_PER_DOC", "20"))

    # Parent-Child 父子分块检索（实验档，默认关）：同块多窗口子块附带块级父内容，
    # 检索命中子块后替换为父正文并按父去重——小块精准召回 + 大块完整上下文。
    RAG_PARENT_CHILD_ENABLED = os.getenv("RAG_PARENT_CHILD_ENABLED", "false").lower() in ("1", "true", "yes")

    # 语义分块（实验档，默认关）：入库时按相邻句 embedding 余弦相似度找语义断点，
    # 替代固定窗口切分——语义完整的分块比等长窗口召回更准。embedding 失败自动
    # 回退固定窗口，ingestion 不因实验特性失败。
    RAG_SEMANTIC_CHUNK_ENABLED = os.getenv("RAG_SEMANTIC_CHUNK_ENABLED", "false").lower() in ("1", "true", "yes")
    RAG_SEMANTIC_SIM_THRESHOLD = float(os.getenv("RAG_SEMANTIC_SIM_THRESHOLD", "0.55"))
    RAG_SEMANTIC_MIN_CHUNK = int(os.getenv("RAG_SEMANTIC_MIN_CHUNK", "120"))

    # P9 is an explicit rollout switch for the bounded single-agent runtime.
    # It wraps the existing read-only React agent; it does not add write tools.
    RAG_AGENT_WORKFLOW_ENABLED = os.getenv("RAG_AGENT_WORKFLOW_ENABLED", "false").lower() == "true"
    RAG_AGENT_TIMEOUT_SECONDS = float(os.getenv("RAG_AGENT_TIMEOUT_SECONDS", "45"))
    RAG_AGENT_MAX_RETRIES = int(os.getenv("RAG_AGENT_MAX_RETRIES", "1"))
    RAG_AGENT_RETRY_DELAY_SECONDS = float(os.getenv("RAG_AGENT_RETRY_DELAY_SECONDS", "0.2"))
    RAG_AGENT_MAX_STEPS = int(os.getenv("RAG_AGENT_MAX_STEPS", "12"))
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

    # 原生 function calling（Batch 2）：生效开关由 Java flag
    # agent.native_tool_calls.enabled 统一治理（V81，默认 FALSE）；
    # env 仅作后端不可达时的降级回退。开启后 provider 不支持时自动降级文本 ReAct。
    AGENT_NATIVE_TOOL_CALLS_ENABLED = os.getenv("AGENT_NATIVE_TOOL_CALLS_ENABLED", "false").lower() == "true"

    # agent.enabled 旗标的降级回退（默认 true 保持既有放行行为）。
    AGENT_ENABLED = os.getenv("AGENT_ENABLED", "true").lower() == "true"

    # ── Embedding 多通道（Batch 5）────────────────────────────────────
    # provider: "ollama"（默认，本地）| "openai_compatible"（通义/OpenAI 等
    # /v1/embeddings 端点）。切换供应商会改变向量维度语义，Milvus collection
    # 需重建索引（openai_compatible 通道对维度做 fail-closed 校验）。
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
    EMBEDDING_OPENAI_BASE_URL = os.getenv("EMBEDDING_OPENAI_BASE_URL", "")
    EMBEDDING_OPENAI_API_KEY = os.getenv("EMBEDDING_OPENAI_API_KEY", "")
    EMBEDDING_OPENAI_MODEL = os.getenv("EMBEDDING_OPENAI_MODEL", "")
    EMBEDDING_OPENAI_DIMENSION = int(os.getenv("EMBEDDING_OPENAI_DIMENSION", "1024"))

    # ── 可插拔内容审核（Batch 7）──────────────────────────────────────
    # provider: "local"（默认，纯本地规则）| "http"（通用 REST 审核端点，
    # 阿里云内容安全/网易易盾等）。外部引擎失败 fail-open（告警放行）。
    MODERATION_PROVIDER = os.getenv("MODERATION_PROVIDER", "local").lower()
    MODERATION_HTTP_ENDPOINT = os.getenv("MODERATION_HTTP_ENDPOINT", "")
    MODERATION_HTTP_API_KEY = os.getenv("MODERATION_HTTP_API_KEY", "")
    MODERATION_HTTP_TIMEOUT_SECONDS = float(os.getenv("MODERATION_HTTP_TIMEOUT_SECONDS", "2"))
    # 响应解析 dot-path（按供应商适配）
    MODERATION_HTTP_FLAGGED_PATH = os.getenv("MODERATION_HTTP_FLAGGED_PATH", "flagged")
    MODERATION_HTTP_CATEGORY_PATH = os.getenv("MODERATION_HTTP_CATEGORY_PATH", "category")
    MODERATION_HTTP_SCORE_PATH = os.getenv("MODERATION_HTTP_SCORE_PATH", "score")

    # ── 语音 STT/TTS（Batch 10，默认关闭）─────────────────────────────
    # 引擎：OpenAI 兼容音频接口（/v1/audio/transcriptions、/v1/audio/speech）。
    # VOICE_ENABLED=false 时端点 503，前端按钮不渲染。
    VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() == "true"
    VOICE_OPENAI_BASE_URL = os.getenv("VOICE_OPENAI_BASE_URL", "")
    VOICE_OPENAI_API_KEY = os.getenv("VOICE_OPENAI_API_KEY", "")
    VOICE_STT_MODEL = os.getenv("VOICE_STT_MODEL", "")
    VOICE_TTS_MODEL = os.getenv("VOICE_TTS_MODEL", "")
    VOICE_TTS_VOICE = os.getenv("VOICE_TTS_VOICE", "alloy")
    VOICE_TIMEOUT_SECONDS = float(os.getenv("VOICE_TIMEOUT_SECONDS", "60"))

    # ── 任务队列外置（Batch 8）────────────────────────────────────────
    # inline（默认）：FastAPI BackgroundTasks 进程内执行，单实例零依赖；
    # arq：解析/向量化任务入 Redis 队列，由独立 worker（arq_worker.py /
    # compose python-ai-worker 服务）消费。入队失败自动降级 inline。
    TASK_QUEUE_MODE = os.getenv("TASK_QUEUE_MODE", "inline").lower()
    ARQ_REDIS_DSN = os.getenv("ARQ_REDIS_DSN", "redis://localhost:6379/2")

    # P10 collaboration remains disabled unless P9 is already enabled.  It is
    # an evidence-review wrapper around the bounded, read-only workflow, not a
    # route to autonomous or cross-knowledge-base tool calls.
    RAG_MULTI_AGENT_ENABLED = os.getenv("RAG_MULTI_AGENT_ENABLED", "false").lower() == "true"
    # Batch 9：多 Agent 编排模式（无 DSL）——pipeline（默认，原 P10）|
    # supervisor（检索→并行补充分析→确定性合并）| handoff（证据不足顺序移交）
    RAG_MULTI_AGENT_MODE = os.getenv("RAG_MULTI_AGENT_MODE", "pipeline").lower()
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

    # ── 长期记忆接线（memory.long_term.enabled，Batch 1）────────────────
    # env 是降级回退值；生效开关由 Java feature flag memory.long_term.enabled
    # 统一治理（默认 FALSE），见 docs/ENVIRONMENT.md。
    MEMORY_LONG_TERM_ENABLED = os.getenv("MEMORY_LONG_TERM_ENABLED", "false").lower() == "true"
    # 每完成 N 轮对话后台触发一次 LLM 记忆抽取（下限 2）
    MEMORY_CONSOLIDATE_EVERY_TURNS = int(os.getenv("MEMORY_CONSOLIDATE_EVERY_TURNS", "6"))
    # 注入上下文的记忆条数上限（Java 侧再钳制到 20）
    MEMORY_CONTEXT_MAX_ENTRIES = int(os.getenv("MEMORY_CONTEXT_MAX_ENTRIES", "8"))
    # 注入块的粗略 token 预算（MemoryManager 按 ~3 char/token 折算）
    MEMORY_CONTEXT_MAX_TOKENS = int(os.getenv("MEMORY_CONTEXT_MAX_TOKENS", "600"))
    # Python→Java internal memory 端点超时
    MEMORY_INTERNAL_TIMEOUT_SECONDS = float(os.getenv("MEMORY_INTERNAL_TIMEOUT_SECONDS", "5"))


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

