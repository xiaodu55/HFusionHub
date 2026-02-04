"""
Cache Manager - 缓存管理器

提供统一的缓存管理功能，避免在每个模块中重复实现缓存逻辑。

功能：
- 统一的缓存键生成
- TTL 支持
- 缓存统计
- 缓存清理
- 缓存装饰器

设计模式：
- 单例模式：全局唯一缓存实例
- 装饰器模式：可装饰任何缓存方法
- 策略模式：支持不同的缓存键生成策略

作者：Claude
日期：2026-07-22
"""

import time
import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple
from functools import wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """
    缓存统计信息

    Attributes:
        hits: 命中次数
        misses: 未命中次数
        size: 当前缓存大小
        evictions: 淘汰次数
    """
    hits: int = 0
    misses: int = 0
    size: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "size": self.size,
            "evictions": self.evictions,
            "hit_rate": round(self.hit_rate, 4),
        }


class CacheManager:
    """
    统一缓存管理器

    提供缓存管理功能，支持 TTL、容量限制、统计等。

    使用示例：
        cache = CacheManager(enabled=True, ttl=3600, max_size=1000)

        # 方式1：直接使用
        cache.set("key", value)
        value = cache.get("key")

        # 方式2：使用装饰器
        @cache.cached(key_func=lambda text, config: f"{text}:{config}")
        async def compress(text, config):
            ...
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl: int = 3600,
        max_size: int = 1000,
        name: str = "default"
    ):
        """
        初始化缓存管理器

        Args:
            enabled: 是否启用缓存
            ttl: 缓存过期时间（秒）
            max_size: 最大缓存容量
            name: 缓存名称（用于日志）
        """
        self.enabled = enabled
        self.ttl = ttl
        self.max_size = max_size
        self.name = name

        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._stats = CacheStats()

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在或已过期则返回 None
        """
        if not self.enabled:
            self._stats.misses += 1
            return None

        if key not in self._cache:
            self._stats.misses += 1
            return None

        value, timestamp = self._cache[key]

        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            del self._cache[key]
            self._stats.misses += 1
            self._stats.size -= 1
            return None

        self._stats.hits += 1
        return value

    def set(self, key: str, value: Any):
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
        """
        if not self.enabled:
            return

        # 检查容量限制
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict()

        self._cache[key] = (value, time.time())
        self._stats.size = len(self._cache)

    def delete(self, key: str):
        """
        删除缓存

        Args:
            key: 缓存键
        """
        if key in self._cache:
            del self._cache[key]
            self._stats.size = len(self._cache)

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._stats.size = 0
        logger.debug(f"Cache '{self.name}' cleared")

    def get_stats(self) -> CacheStats:
        """获取缓存统计"""
        self._stats.size = len(self._cache)
        return self._stats

    def _evict(self):
        """淘汰过期或最旧的缓存"""
        if not self._cache:
            return

        # 先淘汰过期的
        now = time.time()
        expired_keys = [
            key for key, (_, ts) in self._cache.items()
            if now - ts > self.ttl
        ]

        for key in expired_keys:
            del self._cache[key]
            self._stats.evictions += 1

        # 如果还是满的，淘汰最旧的
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
            self._stats.evictions += 1

        self._stats.size = len(self._cache)

    def cached(
        self,
        key_func: Optional[Callable[..., str]] = None,
        ttl: Optional[int] = None
    ):
        """
        缓存装饰器

        Args:
            key_func: 缓存键生成函数，默认使用参数的 MD5
            ttl: 自定义 TTL（可选）

        使用示例：
            @cache.cached(key_func=lambda text, config: f"{text}:{config}")
            async def compress(text, config):
                ...
        """
        cache_ttl = ttl or self.ttl

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self.enabled:
                    return await func(*args, **kwargs)

                # 生成缓存键
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    cache_key = self._generate_key(func.__name__, args, kwargs)

                # 尝试获取缓存
                cached_value = self.get_with_ttl(cache_key, cache_ttl)
                if cached_value is not None:
                    return cached_value

                # 执行函数
                result = await func(*args, **kwargs)

                # 设置缓存
                self.set(cache_key, result)

                return result

            return wrapper
        return decorator

    def get_with_ttl(self, key: str, ttl: int) -> Optional[Any]:
        """
        获取缓存值（使用自定义 TTL）

        Args:
            key: 缓存键
            ttl: 自定义 TTL

        Returns:
            缓存值
        """
        if not self.enabled or key not in self._cache:
            self._stats.misses += 1
            return None

        value, timestamp = self._cache[key]

        if time.time() - timestamp > ttl:
            del self._cache[key]
            self._stats.misses += 1
            self._stats.size -= 1
            return None

        self._stats.hits += 1
        return value

    def _generate_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """
        生成缓存键

        Args:
            func_name: 函数名
            args: 位置参数
            kwargs: 关键字参数

        Returns:
            缓存键
        """
        key_data = {
            "func": func_name,
            "args": str(args),
            "kwargs": str(sorted(kwargs.items()))
        }
        return hashlib.md5(
            json.dumps(key_data, ensure_ascii=False).encode()
        ).hexdigest()


# ==================== 全局缓存实例 ====================

# 默认缓存实例
default_cache = CacheManager(
    enabled=True,
    ttl=3600,
    max_size=1000,
    name="default"
)

# 分类缓存
classification_cache = CacheManager(
    enabled=True,
    ttl=3600,
    max_size=500,
    name="classification"
)

# 压缩缓存
compression_cache = CacheManager(
    enabled=True,
    ttl=1800,
    max_size=500,
    name="compression"
)

# 反思缓存
reflection_cache = CacheManager(
    enabled=True,
    ttl=3600,
    max_size=500,
    name="reflection"
)

# 分解缓存
decomposition_cache = CacheManager(
    enabled=True,
    ttl=3600,
    max_size=200,
    name="decomposition"
)


def generate_cache_key(*args, **kwargs) -> str:
    """
    统一生成缓存键

    Args:
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        缓存键
    """
    key_data = {
        "args": str(args),
        "kwargs": str(sorted(kwargs.items()))
    }
    return hashlib.md5(
        json.dumps(key_data, ensure_ascii=False).encode()
    ).hexdigest()
