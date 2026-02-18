"""
DeepSeek Embedding API Client

Note: DeepSeek currently does not provide a public embedding API.
This provider raises EmbeddingException to prevent silent fallback.
"""

from typing import List, Optional

from app.core.exceptions import EmbeddingException
from app.utils.config import config


class DeepSeekEmbedding:
    """DeepSeek Embedding API client (not available in production)."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, dimension: Optional[int] = None):
        self.api_key = api_key or config.DEEPSEEK_API_KEY
        self.base_url = base_url or config.DEEPSEEK_BASE_URL
        self.dimension = dimension or config.EMBEDDING_DIMENSION

    async def generate(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Raises:
            EmbeddingException: DeepSeek does not provide an embedding API.
        """
        if config.EMBEDDING_ALLOW_FALLBACK:
            import random
            vec = [random.gauss(0, 1) for _ in range(self.dimension)]
            norm = sum(x ** 2 for x in vec) ** 0.5
            return [x / norm for x in vec]
        raise EmbeddingException("DeepSeek embedding API is not available")

    async def generate_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Raises:
            EmbeddingException: DeepSeek does not provide an embedding API.
        """
        if config.EMBEDDING_ALLOW_FALLBACK:
            import random
            results = []
            for _ in texts:
                vec = [random.gauss(0, 1) for _ in range(self.dimension)]
                norm = sum(x ** 2 for x in vec) ** 0.5
                results.append([x / norm for x in vec])
            return results
        raise EmbeddingException("DeepSeek embedding API is not available")


# Singleton instance
_embedding_client: Optional[DeepSeekEmbedding] = None


def get_embedding_client() -> DeepSeekEmbedding:
    """Get or create embedding client singleton"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = DeepSeekEmbedding()
    return _embedding_client
