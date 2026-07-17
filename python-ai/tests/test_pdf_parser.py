
from app.core.parser.pdf_parser import (
    clean_pdf_text,
    is_usable_pdf_text,
    split_pdf_paragraphs,
)


def test_clean_pdf_text_merges_vertical_cjk_lines():
    raw = "预\n估\n处\n理\n时\n间\n\n正文内容继续展示，用于确认文本不是单字竖排。"

    cleaned = clean_pdf_text(raw)

    assert "预估处理时间" in cleaned
    assert "预\n估\n处" not in cleaned


def test_clean_pdf_text_removes_control_chars_and_collapses_duplicate_cjk():
    raw = "\x00预预估估处处理理时时间间\n后续内容用于满足可索引文本长度。"

    cleaned = clean_pdf_text(raw)

    assert "\x00" not in cleaned
    assert "预估处理时间" in cleaned


def test_unusable_pdf_text_rejects_empty_or_tiny_output():
    assert not is_usable_pdf_text("\n")
    assert not is_usable_pdf_text("一\n二\n")


def test_split_pdf_paragraphs_filters_unusable_blocks():
    text = "标题\n这是一段足够长的 PDF 文本，用于生成一个正常段落并进入后续分块流程。"

    paragraphs = split_pdf_paragraphs(clean_pdf_text(text))

    assert len(paragraphs) == 1
    assert "正常段落" in paragraphs[0]
