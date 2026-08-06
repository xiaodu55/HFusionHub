"""
Text chunker with block type identification and outline path tracking
"""

import json
import math
import re
from dataclasses import dataclass, field

from app.core.parser.base import BlockType, ParsedBlock
from app.utils.config import config

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])|(?<=\n)")


@dataclass
class VectorChunk:
    """Chunk for vectorization"""
    chunk_id: str
    index: int
    content: str
    block_type: str
    outline_path: list[str]
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "chunk_id": self.chunk_id,
            "index": self.index,
            "content": self.content,
            "block_type": self.block_type,
            "outline_path": self.outline_path,
            "metadata": self.metadata
        }


class TextChunker:
    """Split parsed blocks into chunks with outline path tracking"""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        """
        Initialize chunker

        Args:
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks in characters
        """
        self.chunk_size = chunk_size or config.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP

    def chunk(self, blocks: list[ParsedBlock], document_id: str) -> list[VectorChunk]:
        """
        Split blocks into chunks

        Args:
            blocks: List of parsed blocks
            document_id: Document identifier

        Returns:
            List of VectorChunk objects
        """
        chunks = []
        chunk_index = 0
        outline_path = []  # Track current heading hierarchy
        block_seq = 0

        for block in blocks:
            # Update outline path based on headings
            if block.block_type == BlockType.HEADING:
                outline_path = self._update_outline_path(outline_path, block)

            # Create chunk(s) from block
            block_chunks = self._chunk_block(
                block=block,
                document_id=document_id,
                chunk_index=chunk_index,
                outline_path=outline_path.copy()
            )

            chunks.extend(block_chunks)

            # Parent-Child（实验特性，RAG_PARENT_CHILD_ENABLED）：同一 block 切出
            # 多个窗口时，为各子块附带块级父内容——检索命中子块（精准），
            # 回答上下文用父块（完整）。单窗口块不加（子块≈父块，无增益且省配额）。
            # metadata 预算守卫：Milvus metadata 字段上限 4000 字符，超限降级丢弃。
            if config.RAG_PARENT_CHILD_ENABLED and len(block_chunks) > 1:
                parent_content = block.content.strip()[:2600]
                parent_id = f"{document_id}_parent_{block_seq:03d}"
                for c in block_chunks:
                    c.metadata["parent_id"] = parent_id
                    c.metadata["parent_content"] = parent_content
                    if len(json.dumps(c.metadata, ensure_ascii=False)) > 3900:
                        c.metadata.pop("parent_content", None)

            block_seq += 1
            chunk_index += len(block_chunks)

        return chunks

    def _update_outline_path(self, current_path: list[str], heading_block: ParsedBlock) -> list[str]:
        """
        Update outline path when encountering a heading

        Args:
            current_path: Current outline path
            heading_block: Heading block

            Updated outline path
        """
        level = heading_block.level or 1
        heading_text = heading_block.content.strip()

        # Remove any levels at or below current heading level
        new_path = []
        for i, item in enumerate(current_path):
            # Estimate level from position (simplified)
            if i < level - 1:
                new_path.append(item)

        # Add current heading
        new_path.append(heading_text)

        return new_path

    def _chunk_block(
        self,
        block: ParsedBlock,
        document_id: str,
        chunk_index: int,
        outline_path: list[str]
    ) -> list[VectorChunk]:
        """
        Create chunk(s) from a single block

        Args:
            block: Parsed block
            document_id: Document identifier
            chunk_index: Starting chunk index
            outline_path: Current outline path

        Returns:
            List of VectorChunk objects
        """
        content = block.content

        # 表格感知分块（Batch 4）：TABLE 块按「行」边界切分并保留表头上下文，
        # 不走句子边界启发式——句子切分会把一行记录拦腰截断，破坏表格语义。
        if block.block_type == BlockType.TABLE:
            return self._chunk_table(
                block=block, document_id=document_id, chunk_index=chunk_index,
                outline_path=outline_path,
            )

        # If content is small enough, return as single chunk
        if len(content) <= self.chunk_size:
            return [VectorChunk(
                chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                index=chunk_index,
                content=content,
                block_type=block.block_type.value,
                outline_path=outline_path,
                metadata={
                    **block.metadata,
                    "char_count": len(content)
                }
            )]

        # 语义分块（实验特性，RAG_SEMANTIC_CHUNK_ENABLED）：按相邻句 embedding
        # 余弦相似度找语义断点。embedding 调用失败或句子少于 2 时返回 None，
        # 回退下方固定窗口——ingestion 绝不因实验特性失败。TABLE 块保持行对齐。
        if config.RAG_SEMANTIC_CHUNK_ENABLED:
            semantic_chunks = self._chunk_semantic(
                block=block, document_id=document_id, chunk_index=chunk_index,
                outline_path=outline_path,
            )
            if semantic_chunks is not None:
                return semantic_chunks

        # Split large content into multiple chunks
        chunks = []
        start = 0
        current_index = chunk_index

        while start < len(content):
            end = min(start + self.chunk_size, len(content))

            # Try to break at sentence or paragraph boundary
            if end < len(content):
                # Look for sentence endings
                for sep in ['\n\n', '\n', '。', '！', '？', '. ', '! ', '? ']:
                    last_sep = content.rfind(sep, start + self.chunk_size // 2, end)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk_content = content[start:end].strip()
            if chunk_content:
                chunks.append(VectorChunk(
                    chunk_id=f"{document_id}_chunk_{current_index:04d}",
                    index=current_index,
                    content=chunk_content,
                    block_type=block.block_type.value,
                    outline_path=outline_path,
                    metadata={
                        **block.metadata,
                        "char_count": len(chunk_content),
                        "start_pos": start,
                        "end_pos": end
                    }
                ))
                current_index += 1

            # If we've reached the end of content, break
            if end >= len(content):
                break

            # Move to next chunk with overlap
            start = end - self.chunk_overlap
            # Ensure we always make progress
            if start <= end - self.chunk_size:
                start = end

        return chunks


    def _chunk_semantic(
        self,
        block: ParsedBlock,
        document_id: str,
        chunk_index: int,
        outline_path: list[str],
    ) -> list[VectorChunk] | None:
        """语义分块：相邻句 embedding 余弦相似度低于阈值处断开，句子永不切断。

        返回 None 表示回退固定窗口（embedding 调用失败 / 句子数 < 2）。
        单句超过 chunk_size 时对该句硬切（极端长句兜底，同表格路径）。
        """
        content = block.content
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(content) if s.strip()]
        if len(sentences) < 2:
            return None

        try:
            # 延迟导入：embedding 依赖 provider 配置，且便于测试注入假实现
            from app.core.embedding import get_embedding_service

            vectors = get_embedding_service().get_embedding_batch(sentences)
        except Exception:  # noqa: BLE001 — 实验特性静默降级，不阻断 ingestion
            return None

        if (
            not vectors
            or len(vectors) != len(sentences)
            or any(not v for v in vectors)
            or len({len(v) for v in vectors}) != 1
        ):
            return None

        chunks: list[VectorChunk] = []
        current_parts: list[str] = []
        current_len = 0
        current_start = 0
        cursor = 0
        current_index = chunk_index

        def _flush() -> None:
            nonlocal current_parts, current_len, current_start, current_index
            if not current_parts:
                return
            joined = "".join(current_parts).strip()
            if joined:
                pieces = _hard_split(joined, self.chunk_size) if len(joined) > self.chunk_size else [joined]
                for piece in pieces:
                    chunks.append(VectorChunk(
                        chunk_id=f"{document_id}_chunk_{current_index:04d}",
                        index=current_index,
                        content=piece,
                        block_type=block.block_type.value,
                        outline_path=outline_path,
                        metadata={
                            **block.metadata,
                            "char_count": len(piece),
                            "start_pos": current_start,
                            "end_pos": current_start + len(joined),
                            "semantic_boundary": True,
                        },
                    ))
                    current_index += 1
            current_parts = []
            current_len = 0
            current_start = cursor

        for i, sentence in enumerate(sentences):
            # 硬上限：加入该句会超出 chunk_size——先落当前块
            if current_parts and current_len + len(sentence) > self.chunk_size:
                _flush()

            # 语义断点：相邻句相似度低于阈值且当前块已达最小长度
            if (
                current_parts
                and current_len >= config.RAG_SEMANTIC_MIN_CHUNK
                and i < len(sentences) - 1
                and _cosine(vectors[i - 1], vectors[i]) < config.RAG_SEMANTIC_SIM_THRESHOLD
            ):
                _flush()

            current_parts.append(sentence)
            current_len += len(sentence)
            cursor += len(sentence)

        _flush()

        if not chunks:
            return None
        return chunks

    def _chunk_table(
        self,
        block: ParsedBlock,
        document_id: str,
        chunk_index: int,
        outline_path: list[str],
    ) -> list[VectorChunk]:
        """表格按行打包：每块尽量容纳整数行，续块带表头前缀保持可解释性。

        单行超限时对该行硬切（极端长单元格的兜底），其余场景永不切断一行。
        """
        content = block.content
        if len(content) <= self.chunk_size:
            return [VectorChunk(
                chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                index=chunk_index,
                content=content,
                block_type=block.block_type.value,
                outline_path=outline_path,
                metadata={**block.metadata, "char_count": len(content)},
            )]

        lines = content.split("\n")
        header = lines[0] if lines else ""
        header_prefix = f"{header}\n（表格续，表头同上）\n" if header else "（表格续）\n"

        chunks: list[VectorChunk] = []
        current_index = chunk_index
        current_lines: list[str] = []
        current_len = 0

        def _flush() -> None:
            nonlocal current_lines, current_len, current_index
            if not current_lines:
                return
            body = "\n".join(current_lines)
            if len(body) > self.chunk_size:
                # 单行超限兜底：对该行按 chunk_size 硬切
                pieces = _hard_split(body, self.chunk_size)
            else:
                pieces = [body]
            for piece in pieces:
                prefix = "" if current_index == chunk_index else header_prefix
                chunk_content = f"{prefix}{piece}"
                chunks.append(VectorChunk(
                    chunk_id=f"{document_id}_chunk_{current_index:04d}",
                    index=current_index,
                    content=chunk_content,
                    block_type=block.block_type.value,
                    outline_path=outline_path,
                    metadata={
                        **block.metadata,
                        "char_count": len(chunk_content),
                        "table_row_aligned": True,
                    },
                ))
                current_index += 1
            current_lines = []
            current_len = 0

        for line in lines:
            if current_lines and current_len + len(line) + 1 > self.chunk_size:
                _flush()
            current_lines.append(line)
            current_len += len(line) + 1
        _flush()
        return chunks


def _hard_split(text: str, size: int) -> list[str]:
    return [text[start:start + size] for start in range(0, len(text), size)]


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度；零向量按不相似（0.0）处理——零向量多来自 embedding 兜底降级。"""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return 0.0
    return dot / norm


def chunk_blocks(blocks: list[ParsedBlock], document_id: str) -> list[VectorChunk]:
    """
    Convenience function to chunk parsed blocks

    Args:
        blocks: List of parsed blocks
        document_id: Document identifier

    Returns:
        List of VectorChunk objects
    """
    chunker = TextChunker()
    return chunker.chunk(blocks, document_id)
