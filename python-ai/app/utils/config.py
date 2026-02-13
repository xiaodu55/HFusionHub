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


config = Config()
