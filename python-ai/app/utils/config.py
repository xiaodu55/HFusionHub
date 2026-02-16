"""
Configuration management for HFusionHub Python AI Engine
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration"""

    # DeepSeek API
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # Milvus
    MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
    MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "hfusionhub_chunks")

    # Server Configuration
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "9000"))
    SERVER_DEBUG = os.getenv("SERVER_DEBUG", "true").lower() == "true"
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

    # Chunking Configuration
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))  # characters
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))  # characters

    # Embedding Configuration
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    EMBEDDING_RETRY_DELAY = float(os.getenv("EMBEDDING_RETRY_DELAY", "1.0"))

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
    RAG_RERANKER_MODE = os.getenv("RAG_RERANKER_MODE", "disabled")
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


config = Config()
