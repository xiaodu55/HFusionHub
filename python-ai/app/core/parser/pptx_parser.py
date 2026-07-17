"""PPTX parser — 纯标准库实现（zipfile + xml.etree），零第三方依赖。

.pptx 本质是 OOXML zip 包：
- ``ppt/slides/slideN.xml``       幻灯片正文（DrawingML）
- ``ppt/notesSlides/notesSlideN.xml`` 演讲者备注

抽取策略（与 DocxParser 对齐的 ParsedBlock 语义）：
- 标题占位符（``<p:ph type="title"|"ctrTitle">``）→ HEADING（level=1）
- 普通文本段落 → PARAGRAPH
- 表格 ``<a:tbl>`` → TABLE（制表符分隔的 TSV 行）
- 备注 → PARAGRAPH（metadata 标注 source=speaker_notes）

设计取舍：不依赖 python-pptx，避免在 pip-compile 哈希锁文件中新增传递依赖；
文本抽取只需要读 XML，zipfile + ElementTree 足够且行为确定。
"""

from __future__ import annotations

import re
import zipfile
from typing import Iterator
from xml.etree import ElementTree as ET

from app.core.parser.base import BaseParser, BlockType, ParsedBlock

# OOXML 命名空间
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

_TAG_TITLE_PH = f"{{{_P_NS}}}ph"          # <p:ph type="title">
_TAG_TABLE = f"{{{_A_NS}}}tbl"            # <a:tbl>
_TAG_TABLE_ROW = f"{{{_A_NS}}}tr"         # <a:tr>
_TAG_TABLE_CELL = f"{{{_A_NS}}}tc"        # <a:tc>
_TAG_PARAGRAPH = f"{{{_A_NS}}}p"          # <a:p>
_TAG_TEXT = f"{{{_A_NS}}}t"               # <a:t>

_SLIDE_XML_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_NOTES_XML_RE = re.compile(r"^ppt/notesSlides/notesSlide(\d+)\.xml$")


class PptxParser(BaseParser):
    """Parse .pptx into blocks: per-slide headings, paragraphs, tables and notes."""

    def parse(self, file_path: str) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        with zipfile.ZipFile(file_path, "r") as archive:
            slide_names = sorted(
                (name for name in archive.namelist() if _SLIDE_XML_RE.match(name)),
                key=_slide_number,
            )
            for name in slide_names:
                number = _slide_number(name)
                root = ET.fromstring(archive.read(name))
                blocks.extend(self._parse_slide(root, number))

                notes_name = f"ppt/notesSlides/notesSlide{number}.xml"
                if notes_name in archive.namelist():
                    notes_root = ET.fromstring(archive.read(notes_name))
                    blocks.extend(self._parse_notes(notes_root, number))

        if not blocks:
            raise ValueError("PPTX 中未提取到任何文本内容（空演示文稿或纯图片页）")
        return blocks

    def _parse_slide(self, root: ET.Element, number: int) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        for shape in root.iter(f"{{{_P_NS}}}sp"):
            # 标题占位符：<p:ph type="title"|"ctrTitle"> 挂在 shape 的 nvSpPr 下
            is_title = any(
                (ph.get("type") or "").lower() in ("title", "ctrtitle")
                for ph in shape.iter(_TAG_TITLE_PH)
            )
            # 表格位于 <p:graphicFrame>，不在 <p:sp> 内，这里不会与表格重复
            paragraphs = [
                t for t in (
                    "".join(node.text or "" for node in paragraph.iter(_TAG_TEXT)).strip()
                    for paragraph in shape.iter(_TAG_PARAGRAPH)
                ) if t
            ]
            if not paragraphs:
                continue
            if is_title:
                blocks.append(ParsedBlock(
                    content=paragraphs[0], block_type=BlockType.HEADING, level=1,
                    metadata={"slide": number},
                ))
                continue
            for paragraph in paragraphs:
                blocks.append(ParsedBlock(
                    content=paragraph, block_type=BlockType.PARAGRAPH,
                    metadata={"slide": number},
                ))

        # 表格与文本形状同级遍历，避免嵌套遗漏
        for table in root.iter(_TAG_TABLE):
            rows = _table_rows(table)
            if rows:
                blocks.append(ParsedBlock(
                    content="\n".join(rows), block_type=BlockType.TABLE,
                    metadata={"slide": number},
                ))
        return blocks

    def _parse_notes(self, root: ET.Element, number: int) -> list[ParsedBlock]:
        text = "\n".join(p for p in _iter_paragraph_text(root) if p)
        if not text.strip():
            return []
        return [ParsedBlock(
            content=text.strip(), block_type=BlockType.PARAGRAPH,
            metadata={"slide": number, "source": "speaker_notes"},
        )]


def _slide_number(name: str) -> int:
    match = _SLIDE_XML_RE.match(name) or _NOTES_XML_RE.match(name)
    return int(match.group(1)) if match else 0


def _iter_paragraph_text(root: ET.Element) -> Iterator[str]:
    for paragraph in root.iter(_TAG_PARAGRAPH):
        text = "".join(node.text or "" for node in paragraph.iter(_TAG_TEXT))
        yield text.strip()


def _iter_paragraph_text(root: ET.Element) -> Iterator[str]:
    for paragraph in root.iter(_TAG_PARAGRAPH):
        text = "".join(node.text or "" for node in paragraph.iter(_TAG_TEXT))
        yield text.strip()


def _table_rows(table: ET.Element) -> list[str]:
    rows: list[str] = []
    for row in table.iter(_TAG_TABLE_ROW):
        cells: list[str] = []
        for cell in row.iter(_TAG_TABLE_CELL):
            cell_text = " ".join(
                "".join(node.text or "" for node in paragraph.iter(_TAG_TEXT)).strip()
                for paragraph in cell.iter(_TAG_PARAGRAPH)
                if "".join(node.text or "" for node in paragraph.iter(_TAG_TEXT)).strip()
            )
            cells.append(cell_text.replace("\t", " "))
        if cells:
            rows.append("\t".join(cells))
    return rows


__all__ = ["PptxParser"]
