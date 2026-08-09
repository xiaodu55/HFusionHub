"""Deterministic, hermetic retrieval index over the committed synthetic KB.

This module backs the PR/offline evaluation track.  It deliberately needs no
database, no vector store and no paid model: it indexes the committed Markdown
under ``evaluation/kb`` with a self-contained BM25 implementation and exposes a
router-shaped ``search`` that satisfies the same contract as the production
``QueryRouter`` (see ``retrieval_evaluator.Router``).

Being fully deterministic, the offline track is reproducible on every machine
and CI run, which is exactly what the Phase-1 baseline gate requires.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.core.rag.query_router import ChannelType, MergedResult, SearchResult
from app.core.rag.tokenization import tokenize  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)

_KB_ROOT = Path(__file__).resolve().parents[3] / "evaluation" / "kb"
_DEFAULT_MANIFEST = _KB_ROOT / "kb_manifest.json"


def _extract_sections(md_text: str) -> list[tuple[str, str]]:
    """Return ``(section_id, section_text)`` pairs from a Markdown document."""
    sections: list[tuple[str, str]] = []
    current_id: str | None = None
    buffer: list[str] = []
    for line in md_text.splitlines():
        match = re.match(r"^##\s+\[([a-z0-9-]+)\]\s*(.*)$", line)
        if match:
            if current_id is not None:
                sections.append((current_id, "\n".join(buffer).strip()))
            current_id = match.group(1)
            buffer = [match.group(2).strip()]
            continue
        if current_id is not None:
            buffer.append(line)
    if current_id is not None:
        sections.append((current_id, "\n".join(buffer).strip()))
    return sections


@dataclass(frozen=True)
class _Bm25Index:
    """Okapi BM25 over a fixed corpus; scores are deterministic."""

    docs: tuple[tuple[str, ...], ...]
    lengths: tuple[int, ...]
    average_length: float
    idf: dict[str, float]
    k1: float = 1.5
    b: float = 0.75

    @classmethod
    def build(cls, corpus: Iterable[Iterable[str]]) -> _Bm25Index:
        docs = tuple(tuple(tokens) for tokens in corpus)
        lengths = tuple(len(doc) for doc in docs)
        average_length = sum(lengths) / len(lengths) if lengths else 0.0
        document_frequencies: Counter[str] = Counter()
        for doc in docs:
            document_frequencies.update(set(doc))
        num_docs = len(docs)
        idf = {
            term: math.log(1 + (num_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequencies.items()
        }
        return cls(
            docs=docs,
            lengths=lengths,
            average_length=average_length,
            idf=idf,
        )

    def score(self, query_terms: Iterable[str], doc_index: int) -> float:
        doc = self.docs[doc_index]
        if not doc:
            return 0.0
        length = self.lengths[doc_index]
        term_frequencies = Counter(doc)
        score = 0.0
        for term in query_terms:
            freq = term_frequencies.get(term)
            if not freq:
                continue
            idf = self.idf.get(term, 0.0)
            if idf <= 0:
                continue
            normalization = self.k1 * (1 - self.b + self.b * length / self.average_length)
            score += idf * (freq * (self.k1 + 1)) / (freq + normalization)
        return score


@dataclass
class SyntheticChunk:
    chunk_id: str
    document_id: int
    document_name: str
    section_title: str
    content: str
    tokens: tuple[str, ...] = field(default_factory=tuple)


class SyntheticIndex:
    """Deterministic in-memory index over ``evaluation/kb``."""

    def __init__(
        self,
        manifest_path: Path = _DEFAULT_MANIFEST,
        min_score: float = 0.0,
    ):
        self.min_score = min_score
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        self.kb_id = int(manifest["kb_id"])
        self.kb_version = str(manifest["version"])
        self.kb_name = str(manifest["name"])

        base_dir = Path(manifest_path).parent
        chunks: list[SyntheticChunk] = []
        for doc_index, doc in enumerate(manifest["documents"], start=1):
            doc_id = doc["doc_id"]
            md_text = (base_dir / doc["filename"]).read_text(encoding="utf-8")
            for section_id, section_text in _extract_sections(md_text):
                tokens = tuple(tokenize(section_text))
                chunks.append(
                    SyntheticChunk(
                        chunk_id=f"{doc_id}#{section_id}",
                        document_id=doc_index,
                        document_name=doc["title"],
                        section_title=section_id,
                        content=section_text,
                        tokens=tokens,
                    )
                )
        self.chunks = chunks
        self.bm25 = _Bm25Index.build(chunk.tokens for chunk in chunks)
        self._content_by_chunk = {chunk.chunk_id: chunk.content for chunk in chunks}

    def get_chunk_content(self, chunk_id: str) -> str | None:
        """返回某 chunk 的原始内容（领域指标做确定性子串匹配用）。"""
        return self._content_by_chunk.get(chunk_id)

    def search_ranked(
        self, query: str, knowledge_base_id: int, top_k: int
    ) -> list[SearchResult]:
        if knowledge_base_id != self.kb_id:
            return []
        query_terms = tokenize(query)
        if not query_terms:
            return []
        scored = [
            (self.bm25.score(query_terms, index), index)
            for index in range(len(self.chunks))
        ]
        scored.sort(key=lambda pair: (-pair[0], self.chunks[pair[1]].chunk_id))
        results: list[SearchResult] = []
        for score, index in scored:
            if score < self.min_score:
                break
            chunk = self.chunks[index]
            results.append(
                SearchResult(
                    content=chunk.content,
                    score=score,
                    source=ChannelType.KEYWORD,
                    document_id=chunk.document_id,
                    metadata={
                        "chunk_id": chunk.chunk_id,
                        "knowledge_base_id": self.kb_id,
                        "document_id": chunk.document_id,
                        "document_name": chunk.document_name,
                        "section_title": chunk.section_title,
                    },
                )
            )
            if len(results) >= top_k:
                break
        return results


class SyntheticRouter:
    """Router-shaped facade satisfying ``retrieval_evaluator.Router``."""

    def __init__(self, index: SyntheticIndex | None = None, min_score: float = 0.0):
        if index is not None:
            self.index = index
        else:
            self.index = SyntheticIndex(min_score=min_score)

    async def search(
        self, query: str, knowledge_base_id: int, top_k: int
    ) -> MergedResult:
        results = self.index.search_ranked(query, knowledge_base_id, top_k)
        return MergedResult(
            results=results,
            total_count=len(results),
            channels_used=[ChannelType.KEYWORD],
        )


def get_synthetic_router(min_score: float = 0.0) -> SyntheticRouter:
    return SyntheticRouter(min_score=min_score)
