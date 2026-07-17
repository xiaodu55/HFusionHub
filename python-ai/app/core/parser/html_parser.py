"""HTML parser — 标准库 html.parser 实现，零第三方依赖。

抽取策略（语义与 DocxParser/MarkdownParser 对齐）：
- ``h1``–``h6``             → HEADING（level 对应）
- ``p`` / ``li``            → PARAGRAPH / LIST
- ``table``                 → TABLE（制表符分隔的 TSV 行，tr/td|th）
- ``script``/``style``      → 跳过
- ``br``                    → 段内换行

不追求渲染级保真，只保证「标题层级 + 正文段落 + 表格结构」可检索。
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser

from app.core.parser.base import BaseParser, BlockType, ParsedBlock

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_SKIP_TAGS = {"script", "style", "template", "head", "noscript"}
_BLOCK_TAGS = {"p", "li", "tr", "div", "section", "article", "blockquote"}
# div/section/article/blockquote 作为块级容器：仅当内部没有更精确的
# p/h/li 结构时，其直接文本才作为段落输出（见 _flush_text）。
_CONTAINER_TAGS = {"div", "section", "article", "blockquote"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[ParsedBlock] = []
        self._skip_depth = 0
        # 当前打开的块级结构栈（h1..h6/p/li/table/容器）
        self._stack: list[str] = []
        self._text_parts: list[str] = []
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._list_stack: list[str] = []

    # ── 标签处理 ────────────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "br":
            self._text_parts.append("\n")
            return
        if tag in _HEADING_TAGS:
            self._push_block(tag)
        elif tag == "p":
            self._push_block(tag)
        elif tag == "li":
            self._push_block(tag)
        elif tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            # 单元格文本累积进 _text_parts，</td> 时收集
            self._push_block("td")
        elif tag in ("ul", "ol"):
            self._list_stack.append(tag)
        elif tag == "table":
            self._stack.append("table")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _HEADING_TAGS and self._stack and self._stack[-1] == tag:
            self._emit_heading(level=_HEADING_TAGS[tag])
        elif tag == "p" and self._stack and self._stack[-1] == "p":
            self._emit_paragraph()
        elif tag == "li" and self._stack and self._stack[-1] == "li":
            self._emit_list_item()
        elif tag in ("td", "th") and self._stack and self._stack[-1] == "td":
            self._collect_cell()
        elif tag == "tr" and self._current_row is not None:
            self._collect_row()
        elif tag == "table" and "table" in self._stack:
            self._emit_table()
        elif tag in _CONTAINER_TAGS:
            self._flush_text_as_paragraph()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._text_parts.append(data)

    # ── 块收集 ──────────────────────────────────────────────────────

    def _push_block(self, tag: str) -> None:
        self._flush_text_as_paragraph()  # 容器内的游离文本
        self._stack.append(tag)
        self._text_parts = []

    def _pop_block(self) -> str:
        tag = self._stack.pop() if self._stack else ""
        self._text_parts = []
        return tag

    def _current_text(self) -> str:
        raw = "".join(self._text_parts)
        return unescape(raw)

    def _emit_heading(self, level: int) -> None:
        text = " ".join(self._current_text().split())
        if text:
            self.blocks.append(ParsedBlock(
                content=text, block_type=BlockType.HEADING, level=level))
        self._pop_block()

    def _emit_paragraph(self) -> None:
        text = self._current_text().strip()
        if text:
            self.blocks.append(ParsedBlock(content=text, block_type=BlockType.PARAGRAPH))
        self._pop_block()

    def _emit_list_item(self) -> None:
        text = self._current_text().strip()
        if text:
            self.blocks.append(ParsedBlock(content=text, block_type=BlockType.LIST))
        self._pop_block()

    def _collect_cell(self) -> None:
        if self._current_row is not None:
            self._current_row.append(" ".join(self._current_text().split()))
        self._pop_block()

    def _collect_row(self) -> None:
        if self._current_row:
            self._table_rows.append(self._current_row)
        self._current_row = None

    def _emit_table(self) -> None:
        # 先把尚未闭合的行收进来
        self._collect_row()
        # 丢弃表格里残留的游离文本（避免与单元格重复）
        self._text_parts = []
        self._stack = [t for t in self._stack if t != "table"]
        if self._table_rows:
            content = "\n".join("\t".join(cell for cell in row) for row in self._table_rows)
            if content.strip():
                self.blocks.append(ParsedBlock(content=content, block_type=BlockType.TABLE))
        self._table_rows = []

    def _flush_text_as_paragraph(self) -> None:
        text = self._current_text().strip()
        self._text_parts = []
        if text:
            self.blocks.append(ParsedBlock(content=text, block_type=BlockType.PARAGRAPH))

    # ── 收尾 ────────────────────────────────────────────────────────

    def close(self) -> None:
        super().close()
        self._flush_text_as_paragraph()
        self._collect_row()


class HtmlParser(BaseParser):
    """Parse .html/.htm into blocks: headings, paragraphs, lists and tables."""

    def parse(self, file_path: str) -> list[ParsedBlock]:
        from pathlib import Path

        raw = Path(file_path).read_bytes()
        text = self._decode(raw)
        extractor = _TextExtractor()
        extractor.feed(text)
        extractor.close()
        if not extractor.blocks:
            raise ValueError("HTML 中未提取到任何文本内容（纯脚本/空页面）")
        return extractor.blocks

    @staticmethod
    def _decode(raw: bytes) -> str:
        """UTF-8 优先，按 meta charset 降级，严格失败时用 replace 兜底。"""
        for encoding in ("utf-8", "gb18030"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")


__all__ = ["HtmlParser"]
