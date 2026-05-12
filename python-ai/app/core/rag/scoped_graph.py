"""Knowledge-base scoped graph index used by the production GraphRAG channel.

The older :mod:`knowledge_graph` module is an exploratory, global graph.  It
must never be queried for a selected knowledge base because it cannot prove
where an entity or relation came from.  This module intentionally keeps a
smaller graph whose every node and edge has source chunk evidence and a
``knowledge_base_id``.  Results are returned only when that source chunk is
still present in the currently selected knowledge base.

The first indexer uses deterministic entity co-occurrence.  This mirrors the
cheap extraction option used by FastGraphRAG while keeping the ingestion path
offline and repeatable.  A later LLM extractor can enrich the same schema, but
cannot omit the scope or source-evidence fields.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


_LATIN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,}")
_HAN_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_COMMON_TERMS = {
    "about", "after", "before", "document", "from", "into", "that",
    "the", "this", "with", "以及", "但是", "可以", "我们", "相关", "其中",
    "内容", "文档", "知识", "用于", "通过", "进行", "一个", "什么", "如何",
}


def _stable_id(*parts: object) -> str:
    value = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _entity_terms(text: str, limit: int = 12) -> List[str]:
    """Extract deterministic, language-neutral candidate entities.

    Latin identifiers are retained as whole tokens.  Chinese runs are split
    into overlapping two-character terms; it is deliberately conservative and
    bounded so one long paragraph cannot create an unbounded clique.
    """
    candidates: List[str] = []
    candidates.extend(_LATIN_TERM.findall(text))
    for run in _HAN_RUN.findall(text):
        candidates.extend(run[index:index + 2] for index in range(len(run) - 1))

    unique: List[str] = []
    seen = set()
    for candidate in candidates:
        normalized = _normalise(candidate)
        if len(normalized) < 2 or normalized in _COMMON_TERMS or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate.strip())
        if len(unique) >= limit:
            break
    return unique


def _flatten_chunks(store: Mapping[str, Sequence[Mapping[str, Any]]]) -> Iterable[Mapping[str, Any]]:
    for chunks in store.values():
        for chunk in chunks:
            if isinstance(chunk, Mapping):
                yield chunk


class ScopedGraphStore:
    """A durable graph with mandatory KB and source-chunk provenance."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = Lock()
        # Read-through cache keyed by (mtime_ns, size).  All callers of
        # ``_read`` hold ``self._lock``, so the cache fields need no extra
        # locking of their own.  ``_write`` clears it explicitly so the
        # same-mtime edge case cannot serve stale data.
        self._cache_key: Optional[Tuple[int, int]] = None
        self._cache_payload: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def _read(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            st = self.path.stat()
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if key is not None and key == self._cache_key and self._cache_payload is not None:
            return self._cache_payload
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("nodes"), list) and isinstance(payload.get("edges"), list):
                result: Dict[str, List[Dict[str, Any]]] = {"nodes": payload["nodes"], "edges": payload["edges"]}
            else:
                result = {"nodes": [], "edges": []}
        except (OSError, TypeError, ValueError):
            result = {"nodes": [], "edges": []}
        self._cache_key = key
        self._cache_payload = result
        return result

    def _write(self, payload: Dict[str, List[Dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="rag_graph_", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
            os.replace(temporary, self.path)
            # Invalidate the read cache: the file has been replaced in place
            # (same path), so force the next _read to reload.
            self._cache_key = None
            self._cache_payload = None
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _chunk_value(chunk: Any, name: str, default: Any = None) -> Any:
        if isinstance(chunk, Mapping):
            return chunk.get(name, default)
        return getattr(chunk, name, default)

    def replace_document(self, knowledge_base_id: int, document_id: str, chunks: Sequence[Any],
                         tenant_id: Optional[int] = None) -> None:
        """Replace one document's graph evidence after vector indexing succeeds."""
        if knowledge_base_id is None:
            raise ValueError("knowledge_base_id is required for graph indexing")
        kb_id = int(knowledge_base_id)
        document_id = str(document_id)
        if tenant_id is None:
            from app.core.tenant.context import require_tenant_id
            tenant_id = require_tenant_id()  # fail-closed: no default tenant
        with self._lock:
            graph = self._read()

            def _owner(item: Dict[str, Any]) -> int:
                return int(item.get("tenant_id", 1))

            nodes = []
            for node in graph["nodes"]:
                if _owner(node) != tenant_id:
                    nodes.append(node)
                    continue
                if int(node.get("knowledge_base_id", -1)) == kb_id and any(
                    str(item.get("document_id")) == document_id for item in node.get("evidence", [])
                ):
                    evidence = [item for item in node.get("evidence", []) if str(item.get("document_id")) != document_id]
                    if evidence:
                        nodes.append({**node, "evidence": evidence})
                    continue
                nodes.append(node)
            edges = []
            for edge in graph["edges"]:
                if _owner(edge) != tenant_id:
                    edges.append(edge)
                    continue
                if int(edge.get("knowledge_base_id", -1)) == kb_id and any(
                    str(item.get("document_id")) == document_id for item in edge.get("evidence", [])
                ):
                    evidence = [item for item in edge.get("evidence", []) if str(item.get("document_id")) != document_id]
                    if evidence:
                        edges.append({**edge, "evidence": evidence})
                    continue
                edges.append(edge)
            nodes = [node for node in nodes if node.get("evidence")]
            edges = [edge for edge in edges if edge.get("evidence")]
            nodes_by_id = {str(node["id"]): node for node in nodes}
            edges_by_id = {str(edge["id"]): edge for edge in edges}

            for chunk in chunks:
                chunk_id = str(self._chunk_value(chunk, "chunk_id", ""))
                content = str(self._chunk_value(chunk, "content", ""))
                if not chunk_id or not content:
                    continue
                terms = _entity_terms(content)
                node_ids: List[str] = []
                for term in terms:
                    normalized = _normalise(term)
                    node_id = _stable_id("node", kb_id, normalized)
                    node = nodes_by_id.setdefault(node_id, {
                        "id": node_id,
                        "knowledge_base_id": kb_id,
                        "tenant_id": tenant_id,
                        "name": term,
                        "normalized_name": normalized,
                        "evidence": [],
                    })
                    evidence = {"chunk_id": chunk_id, "document_id": document_id}
                    if evidence not in node["evidence"]:
                        node["evidence"].append(evidence)
                    node_ids.append(node_id)

                for index, source_id in enumerate(node_ids):
                    for target_id in node_ids[index + 1:]:
                        left, right = sorted((source_id, target_id))
                        edge_id = _stable_id("edge", kb_id, left, right, "co_occurs_in")
                        edge = edges_by_id.setdefault(edge_id, {
                            "id": edge_id,
                            "knowledge_base_id": kb_id,
                            "tenant_id": tenant_id,
                            "source_id": left,
                            "target_id": right,
                            "relation_type": "co_occurs_in",
                            "evidence": [],
                        })
                        evidence = {"chunk_id": chunk_id, "document_id": document_id}
                        if evidence not in edge["evidence"]:
                            edge["evidence"].append(evidence)

            self._write({"nodes": list(nodes_by_id.values()), "edges": list(edges_by_id.values())})

    def remove_document(self, knowledge_base_id: int, document_id: str, tenant_id: Optional[int] = None) -> None:
        self.replace_document(knowledge_base_id, document_id, [])

    def remove_document_from_tenant_scopes(self, tenant_id: int, document_id: str) -> None:
        """Garbage-collect a deleted document, scoped to ONE tenant.

        The active tenant is a hard isolation boundary: a cross-tenant request
        must never be able to purge another tenant's graph content.  Only nodes
        and edges that belong to the given tenant and reference the document are
        touched; nodes without a tenant stamp (pre-tenant migration) are treated
        as legacy tenant 1.
        """
        document_id = str(document_id)
        with self._lock:
            graph = self._read()
            nodes = []
            for node in graph["nodes"]:
                owner = int(node.get("tenant_id", 1))
                if owner != tenant_id:
                    nodes.append(node)
                    continue
                evidence = [item for item in node.get("evidence", []) if str(item.get("document_id")) != document_id]
                if evidence:
                    nodes.append({**node, "evidence": evidence})
            edges = []
            for edge in graph["edges"]:
                owner = int(edge.get("tenant_id", 1))
                if owner != tenant_id:
                    edges.append(edge)
                    continue
                evidence = [item for item in edge.get("evidence", []) if str(item.get("document_id")) != document_id]
                if evidence:
                    edges.append({**edge, "evidence": evidence})
            self._write({"nodes": nodes, "edges": edges})

    def stats(self, knowledge_base_id: int) -> Dict[str, int]:
        kb_id = int(knowledge_base_id)
        with self._lock:
            graph = self._read()
        return {
            "knowledge_base_id": kb_id,
            "node_count": sum(int(node.get("knowledge_base_id", -1)) == kb_id for node in graph["nodes"]),
            "edge_count": sum(int(edge.get("knowledge_base_id", -1)) == kb_id for edge in graph["edges"]),
        }

    def search(
        self,
        query: str,
        knowledge_base_id: int,
        chunks_store: Mapping[str, Sequence[Mapping[str, Any]]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Return source-backed graph candidates, failing closed on scope."""
        if knowledge_base_id is None:
            return []
        kb_id = int(knowledge_base_id)
        with self._lock:
            graph = self._read()
        visible_chunks = {
            str(chunk.get("chunk_id")): chunk
            for chunk in _flatten_chunks(chunks_store)
            if chunk.get("knowledge_base_id") == kb_id and chunk.get("chunk_id")
        }
        if not visible_chunks:
            return []

        query_terms = [_normalise(term) for term in _entity_terms(query, limit=24)]
        if not query_terms:
            return []
        nodes = {
            str(node["id"]): node
            for node in graph["nodes"]
            if int(node.get("knowledge_base_id", -1)) == kb_id
        }
        matched: Dict[str, float] = {}
        for node_id, node in nodes.items():
            name = str(node.get("normalized_name", ""))
            score = max((1.0 if term == name else 0.72 if term in name or name in term else 0.0) for term in query_terms)
            if score:
                matched[node_id] = score
        if not matched:
            return []

        candidates: Dict[str, Dict[str, Any]] = {}
        def add_evidence(evidence: Mapping[str, Any], score: float, path: List[str], entity_names: List[str]) -> None:
            chunk_id = str(evidence.get("chunk_id", ""))
            chunk = visible_chunks.get(chunk_id)
            if not chunk:
                return
            existing = candidates.setdefault(chunk_id, {
                "content": str(chunk.get("content", "")),
                "score": 0.0,
                "document_id": chunk.get("document_id"),
                "metadata": {
                    "chunk_id": chunk_id,
                    "knowledge_base_id": kb_id,
                    "outline_path": chunk.get("outline_path", []),
                    "graph": {"entities": [], "paths": [], "relation_types": []},
                },
            })
            existing["score"] = max(existing["score"], score)
            graph_metadata = existing["metadata"]["graph"]
            graph_metadata["entities"] = sorted(set(graph_metadata["entities"]) | set(entity_names))
            if path not in graph_metadata["paths"]:
                graph_metadata["paths"].append(path)
            if len(path) == 3 and path[1] not in graph_metadata["relation_types"]:
                graph_metadata["relation_types"].append(path[1])

        for node_id, node_score in matched.items():
            node = nodes[node_id]
            name = str(node.get("name", ""))
            for evidence in node.get("evidence", []):
                add_evidence(evidence, node_score * 0.8, [name], [name])

        for edge in graph["edges"]:
            if int(edge.get("knowledge_base_id", -1)) != kb_id:
                continue
            source_id, target_id = str(edge.get("source_id")), str(edge.get("target_id"))
            source_score, target_score = matched.get(source_id), matched.get(target_id)
            if source_score is None and target_score is None:
                continue
            source_name = str(nodes.get(source_id, {}).get("name", ""))
            target_name = str(nodes.get(target_id, {}).get("name", ""))
            relation = str(edge.get("relation_type", "co_occurs_in"))
            edge_score = (0.92 if source_score is not None and target_score is not None else 0.66) * max(source_score or 0, target_score or 0)
            for evidence in edge.get("evidence", []):
                add_evidence(evidence, edge_score, [source_name, relation, target_name], [source_name, target_name])

        return sorted(candidates.values(), key=lambda item: item["score"], reverse=True)[:top_k]


_stores: Dict[str, ScopedGraphStore] = {}
_stores_lock = Lock()


def get_scoped_graph_store(path: str | Path) -> ScopedGraphStore:
    key = str(Path(path))
    with _stores_lock:
        return _stores.setdefault(key, ScopedGraphStore(key))
