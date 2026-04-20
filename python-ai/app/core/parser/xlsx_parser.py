"""
XLSX table parser — converts .xlsx workbooks into TABLE blocks.

Uses only the standard library (zipfile + xml.etree) so no new pinned
dependency is required.  Handles shared strings, inline strings and numeric
cells.  Each worksheet becomes a HEADING block (sheet name) followed by
TABLE blocks of at most ``MAX_ROWS_PER_BLOCK`` data rows.
"""

import re
import zipfile
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from app.core.parser.base import BaseParser, ParsedBlock, BlockType

MAX_ROWS_PER_BLOCK = 50

_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _q(tag: str) -> str:
    return f"{{{_NS['main']}}}{tag}"


def _cell_text(cell: ET.Element, shared_strings: List[str]) -> str:
    """Extract the visible text of a worksheet cell."""
    cell_type = cell.get("t")
    if cell_type == "s":  # shared string
        v = cell.find(_q("v"))
        if v is None or v.text is None:
            return ""
        try:
            index = int(v.text)
            return shared_strings[index] if 0 <= index < len(shared_strings) else ""
        except (ValueError, IndexError):
            return ""
    if cell_type == "inlineStr":  # inline string
        parts = []
        for t in cell.iter(_q("t")):
            if t.text:
                parts.append(t.text)
        return "".join(parts)
    # number / str / default
    v = cell.find(_q("v"))
    if v is not None and v.text is not None:
        text = v.text.strip()
        if cell_type == "str" or cell_type == "b":
            return text
        # Trim trailing zeros on integral floats like "12.0" → "12"
        return re.sub(r"\.0+$", "", text)
    return ""


class XlsxParser(BaseParser):
    """Parse XLSX workbooks into HEADING + TABLE blocks."""

    def parse(self, file_path: str) -> List[ParsedBlock]:
        with zipfile.ZipFile(file_path) as zf:
            shared_strings = self._read_shared_strings(zf)
            sheets = self._read_sheet_names(zf)
            blocks: List[ParsedBlock] = []
            for sheet_id, (name, path) in enumerate(sheets, start=1):
                rows = self._read_sheet_rows(zf, path, shared_strings)
                if not rows:
                    continue
                blocks.append(ParsedBlock(
                    content=name or f"工作表{sheet_id}",
                    block_type=BlockType.HEADING,
                    level=1,
                    metadata={"sheet": name or f"sheet{sheet_id}"},
                ))
                blocks.extend(self._rows_to_table_blocks(rows, name or f"sheet{sheet_id}"))
        return blocks

    @staticmethod
    def _read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
        if "xl/sharedStrings.xml" not in zf.namelist():
            return []
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        result = []
        for si in root.findall(_q("si")):
            parts = []
            for t in si.iter(_q("t")):
                if t.text:
                    parts.append(t.text)
            result.append("".join(parts))
        return result

    @staticmethod
    def _read_sheet_names(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
        """Return [(sheet_name, sheet_xml_path)] in workbook order."""
        root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        # Map relationship id → target path
        rel_map: Dict[str, str] = {}
        for rel in rels:
            rel_id = rel.get("Id")
            target = rel.get("Target", "")
            if rel_id and target:
                rel_map[rel_id] = target.lstrip("/")

        sheets = []
        for sheet in root.iter(_q("sheet")):
            name = sheet.get("name") or ""
            rid = sheet.get(f"{{{_NS['rel']}}}id") or sheet.get("r:id")
            target = rel_map.get(rid or "", "")
            # Normalise relative worksheet path (e.g. "worksheets/sheet1.xml")
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            sheets.append((name, target))
        return sheets

    @staticmethod
    def _read_sheet_rows(
        zf: zipfile.ZipFile,
        sheet_path: str,
        shared_strings: List[str],
    ) -> List[List[str]]:
        if sheet_path not in zf.namelist():
            return []
        root = ET.fromstring(zf.read(sheet_path))
        rows: List[List[str]] = []
        for row in root.iter(_q("row")):
            cells = {}
            for cell in row.findall(_q("c")):
                ref = cell.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                cells[col] = _cell_text(cell, shared_strings)
            if not cells:
                continue
            # Build a dense row using spreadsheet column order.
            max_col = max((_col_index(c) for c in cells), default=-1)
            dense = [cells.get(_col_name(i), "") for i in range(max_col + 1)]
            if any(str(v).strip() for v in dense):
                rows.append(dense)
        return rows

    @staticmethod
    def _rows_to_table_blocks(rows: List[List[str]], sheet_name: str) -> List[ParsedBlock]:
        header = rows[0]
        data_rows = rows[1:]
        blocks: List[ParsedBlock] = []
        for start in range(0, len(data_rows), MAX_ROWS_PER_BLOCK):
            group = data_rows[start:start + MAX_ROWS_PER_BLOCK]
            content_lines = ["| " + " | ".join(_escape_cell(h) for h in header) + " |"]
            content_lines.append("| " + " | ".join("---" for _ in header) + " |")
            for row in group:
                padded = list(row) + [""] * (len(header) - len(row))
                content_lines.append("| " + " | ".join(_escape_cell(v) for v in padded[:len(header)]) + " |")
            blocks.append(ParsedBlock(
                content="\n".join(content_lines),
                block_type=BlockType.TABLE,
                metadata={
                    "sheet": sheet_name,
                    "rows": len(group),
                    "columns": len(header),
                },
            ))
        return blocks


def _col_index(name: str) -> int:
    """A → 0, B → 1, ..., AA → 26."""
    index = 0
    for ch in name:
        index = index * 26 + (ord(ch.upper()) - ord("A") + 1)
    return index - 1


def _col_name(index: int) -> str:
    """0 → A, 1 → B, ..., 26 → AA."""
    name = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = chr(ord("A") + rem) + name
    return name


def _escape_cell(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()
