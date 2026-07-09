"""
Text chunker with block type identification and outline path tracking
"""

from dataclasses import dataclass, field
from typing import List, Optional
from app.core.parser.base import ParsedBlock, BlockType
from app.utils.config import config


@dataclass
class VectorChunk:
    """Chunk for vectorization"""
    chunk_id: str
    index: int
    content: str
    block_type: str
    outline_path: List[str]
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

    def chunk(self, blocks: List[ParsedBlock], document_id: str) -> List[VectorChunk]:
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
            chunk_index += len(block_chunks)

        return chunks

    def _update_outline_path(self, current_path: List[str], heading_block: ParsedBlock) -> List[str]:
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
        outline_path: List[str]
    ) -> List[VectorChunk]:
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


    def _chunk_table(
        self,
        block: ParsedBlock,
        document_id: str,
        chunk_index: int,
        outline_path: List[str],
    ) -> List[VectorChunk]:
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

        chunks: List[VectorChunk] = []
        current_index = chunk_index
        current_lines: List[str] = []
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


def _hard_split(text: str, size: int) -> List[str]:
    return [text[start:start + size] for start in range(0, len(text), size)]


def chunk_blocks(blocks: List[ParsedBlock], document_id: str) -> List[VectorChunk]:
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
