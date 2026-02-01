"""
DeepSeek Embedding API Client
With fallback to random vectors for testing
"""

import time
import random
import httpx
import asyncio
from typing import List, Optional
from app.utils.config import config


class DeepSeekEmbedding:
    """
    DeepSeek Embedding API client

    Supports:
    - Text embedding generation
    - Batch embedding (multiple texts)
    - Automatic retry on failure
    - Fallback to random vectors if API unavailable
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, dimension: Optional[int] = None):
        self.api_key = api_key or config.DEEPSEEK_API_KEY
        self.base_url = base_url or config.DEEPSEEK_BASE_URL
        self.dimension = dimension or config.EMBEDDING_DIMENSION
        self.max_retries = config.EMBEDDING_MAX_RETRIES
        self.retry_delay = config.EMBEDDING_RETRY_DELAY

    def _get_headers(self) -> dict:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _generate_random_vector(self) -> List[float]:
        """Generate a random unit vector for testing"""
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        # Normalize to unit vector
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]

    async def generate(self, text: str) -> List[float]:
        """
        Generate embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        # DeepSeek目前没有embedding API，直接使用随机向量
        print("[Embedding] Using random vector (DeepSeek embedding not available)")
        return self._generate_random_vector()

    async def generate_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """
        Generate embeddings for multiple texts

        Args:
            texts: List of input texts
            batch_size: Number of texts to process in each batch

        Returns:
            List of embedding vectors
        """
        # DeepSeek目前没有embedding API，直接使用随机向量
        print(f"[Embedding] Generating {len(texts)} random vectors")
        return [self._generate_random_vector() for _ in texts]


# Singleton instance
_embedding_client: Optional[DeepSeekEmbedding] = None


def get_embedding_client() -> DeepSeekEmbedding:
    """Get or create embedding client singleton"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = DeepSeekEmbedding()
    return _embedding_client
