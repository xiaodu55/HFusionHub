from app.core.chunker.quality import assess_chunk_quality
from app.core.chunker.text_chunker import VectorChunk
from app.core.parser.base import BlockType, ParsedBlock


def test_chunk_quality_reports_duplicate_and_short_chunk_warnings():
    blocks = [ParsedBlock(content="Heading", block_type=BlockType.HEADING, level=1)]
    chunks = [
        VectorChunk("a", 0, "tiny", "PARAGRAPH", []),
        VectorChunk("b", 1, "tiny", "PARAGRAPH", []),
        VectorChunk("c", 2, "small", "PARAGRAPH", []),
        VectorChunk("d", 3, "brief", "PARAGRAPH", []),
        VectorChunk("e", 4, "short", "PARAGRAPH", []),
    ]

    report = assess_chunk_quality(blocks, chunks)

    assert report.duplicate_chunk_count == 1
    assert report.short_chunk_count == 5
    assert "duplicate_chunks_detected" in report.warnings
    assert "many_short_chunks" in report.warnings
    assert "heading_context_not_preserved" in report.warnings
