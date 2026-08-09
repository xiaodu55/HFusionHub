"""Deterministic tokenization shared by retrieval, compression and evaluation.

CJK-bigram tokenizer: ASCII words/numbers plus character bigrams over CJK runs.
No external dependency (no jieba) so it stays deterministic and hermetic —
the same property that makes the offline evaluation track reproducible, and
that lets the compressor's query-relevance signal be unit-testable without a
segmenter model.

``app.core.rag.synthetic_index`` re-exports :func:`tokenize` for backward
compatibility with existing imports.
"""

from __future__ import annotations

import re

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[0-9]+)?")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Deterministic tokenization: ASCII words/numbers plus CJK bigrams."""
    tokens: list[str] = []
    tokens.extend(m.group(0).lower() for m in _ASCII_TOKEN_RE.finditer(text))
    for run in _CJK_RUN_RE.findall(text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens
