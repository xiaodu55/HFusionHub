"""Deterministic quality checks for parsed document chunks.

These checks are intentionally model-free, so they can run on every ingestion
without external cost. They flag parser or chunker regressions before they
become difficult-to-diagnose retrieval failures; warnings do not reject a
document because valid short documents and code snippets exist.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True)
class ChunkQualityReport:
    block_count: int
    chunk_count: int
    total_characters: int
    median_chunk_characters: float
    short_chunk_count: int
    duplicate_chunk_count: int
    chunks_with_outline_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_chunk_quality(blocks: Iterable[Any], chunks: Iterable[Any], *, short_chunk_threshold: int = 40) -> ChunkQualityReport:
    block_list = list(blocks)
    chunk_list = list(chunks)
    contents = [str(chunk.content).strip() for chunk in chunk_list]
    lengths = [len(content) for content in contents]
    non_empty = [content for content in contents if content]
    duplicate_count = sum(count - 1 for count in Counter(non_empty).values() if count > 1)
    short_count = sum(0 < length < short_chunk_threshold for length in lengths)
    outlined = sum(bool(getattr(chunk, "outline_path", [])) for chunk in chunk_list)
    warnings: list[str] = []
    if not chunk_list:
        warnings.append("no_chunks_created")
    if chunk_list and not non_empty:
        warnings.append("all_chunks_empty")
    if duplicate_count:
        warnings.append("duplicate_chunks_detected")
    if len(chunk_list) >= 5 and short_count / len(chunk_list) > 0.5:
        warnings.append("many_short_chunks")
    if block_list and any(getattr(block, "level", None) for block in block_list) and not outlined:
        warnings.append("heading_context_not_preserved")
    return ChunkQualityReport(
        block_count=len(block_list),
        chunk_count=len(chunk_list),
        total_characters=sum(lengths),
        median_chunk_characters=float(median(lengths)) if lengths else 0.0,
        short_chunk_count=short_count,
        duplicate_chunk_count=duplicate_count,
        chunks_with_outline_count=outlined,
        warnings=warnings,
    )
