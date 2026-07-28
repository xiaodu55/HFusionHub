"""
PDF document parser.
"""

import re
import unicodedata
from typing import Iterable

from app.core.exceptions import ParsingException
from app.core.parser.base import BaseParser, BlockType, ParsedBlock

_CJK_RE = re.compile(r"[\u2e80-\u2eff\u2f00-\u2fdf\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_DUPLICATE_ARTIFACT_RE = re.compile(r"([\u2e80-\u2eff\u2f00-\u2fdf\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff。、，,；;：:！？!?（）()])\1+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class PDFParser(BaseParser):
    """Parse PDF files into text blocks."""

    def parse(self, file_path: str) -> list[ParsedBlock]:
        """Parse PDF file into paragraph blocks."""
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError("pypdf is required for PDF parsing. Install with: pip install pypdf") from exc

        reader = PdfReader(file_path)
        blocks: list[ParsedBlock] = []

        for page_num, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            cleaned_text = clean_pdf_text(raw_text)
            if not is_usable_pdf_text(cleaned_text):
                continue

            for paragraph in split_pdf_paragraphs(cleaned_text):
                blocks.append(ParsedBlock(
                    content=paragraph,
                    block_type=BlockType.PARAGRAPH,
                    metadata={
                        "page": page_num,
                        "char_count": len(paragraph),
                    },
                ))

        if not blocks:
            raise ParsingException("PDF 未提取到可索引文本。该文件可能是扫描件、图片型 PDF，或文本编码异常；请使用可复制文字的 PDF 或先 OCR 后再上传。")

        return blocks


def clean_pdf_text(text: str) -> str:
    """Normalize pypdf text and repair common CJK extraction artifacts."""
    if not text:
        return ""

    text = text.replace("\ufeff", "")
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [_normalize_inline_spaces(line.strip()) for line in text.split("\n")]
    lines = [line for line in lines if line]
    lines = _merge_fragment_lines(lines)

    return _repair_duplicate_artifacts("\n".join(lines)).strip()


def split_pdf_paragraphs(text: str) -> list[str]:
    """Split normalized PDF text into paragraph-sized blocks."""
    paragraphs: list[str] = []
    current: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(_normalize_inline_spaces(" ".join(current)))
                current = []
            continue

        if current and _should_start_new_paragraph(current[-1], stripped):
            paragraphs.append(_normalize_inline_spaces(" ".join(current)))
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        paragraphs.append(_normalize_inline_spaces(" ".join(current)))

    return [p for p in paragraphs if is_usable_pdf_text(p)]


def is_usable_pdf_text(text: str) -> bool:
    """Reject empty, control-heavy, or near-garbage PDF extraction output."""
    stripped = text.strip()
    if len(stripped) < 20:
        return False

    printable = sum(1 for ch in stripped if ch.isprintable() and not ch.isspace())
    if printable < 20:
        return False

    bad_chars = stripped.count("\ufffd") + stripped.count("□")
    if printable and bad_chars / printable > 0.05:
        return False

    lines = [line.strip() for line in stripped.split("\n") if line.strip()]
    if len(lines) >= 20:
        single_char_lines = sum(1 for line in lines if len(line) == 1)
        if single_char_lines / len(lines) > 0.7:
            return False

    return True


def _merge_fragment_lines(lines: Iterable[str]) -> list[str]:
    merged: list[str] = []
    fragment_buffer: list[str] = []

    def flush_fragment_buffer() -> None:
        nonlocal fragment_buffer
        if fragment_buffer:
            merged.append(_repair_duplicate_artifacts("".join(fragment_buffer)))
            fragment_buffer = []

    for line in lines:
        if _is_fragment_line(line):
            fragment_buffer.append(line)
            continue

        flush_fragment_buffer()
        if merged and _should_join_lines(merged[-1], line):
            merged[-1] = f"{merged[-1]}{line}"
        else:
            merged.append(line)

    flush_fragment_buffer()
    return merged


def _repair_duplicate_artifacts(text: str) -> str:
    if _duplicate_artifact_ratio(text) < 0.08:
        return _collapse_repeated_cjk(text)
    return _DUPLICATE_ARTIFACT_RE.sub(r"\1", text)


def _duplicate_artifact_ratio(text: str) -> float:
    relevant = 0
    duplicated = 0
    previous = ""
    for ch in text:
        if not _CJK_RE.match(ch) and ch not in "。、，,；;：:！？!?（）()":
            previous = ch
            continue
        relevant += 1
        if previous == ch:
            duplicated += 1
        previous = ch
    if relevant == 0:
        return 0
    return duplicated / relevant


def _collapse_repeated_cjk(text: str) -> str:
    # Some embedded-font PDFs are extracted as duplicated Chinese characters,
    # e.g. "预预估估处处理理".  Collapse only long CJK-heavy runs so normal
    # repeated words like "人人" are not broadly rewritten.
    def collapse_run(match: re.Match[str]) -> str:
        run = match.group(0)
        collapsed = []
        i = 0
        while i < len(run):
            collapsed.append(run[i])
            if i + 1 < len(run) and run[i] == run[i + 1]:
                i += 2
            else:
                i += 1
        return "".join(collapsed)

    return re.sub(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{8,}", collapse_run, text)


def _normalize_inline_spaces(text: str) -> str:
    text = re.sub(r"[\t\u3000]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"(?<=[\u3400-\u4dbf\u4e00-\u9fff]) (?=[\u3400-\u4dbf\u4e00-\u9fff])", "", text)
    return text.strip()


def _is_fragment_line(line: str) -> bool:
    if len(line) == 1:
        return True
    if len(line) == 2 and line[0] == line[1]:
        return True
    return False


def _should_join_lines(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    if previous[-1] in "。！？!?；;：:" or current[0].isdigit():
        return False
    return bool(_CJK_RE.search(previous[-1]) and _CJK_RE.search(current[0]))


def _should_start_new_paragraph(previous: str, current: str) -> bool:
    if len(current) <= 4 and current.endswith(("章", "节")):
        return True
    if re.match(r"^\d+(\.\d+)*[、.\s]", current):
        return True
    if previous.endswith(("。", "！", "？", ".", "!", "?")) and len(current) > 30:
        return True
    return False
