"""
CSV table parser — converts CSV files into TABLE blocks.

Design: the first non-empty row is treated as the header.  Rows are grouped
into TABLE blocks of at most ``MAX_ROWS_PER_BLOCK`` data rows so each block
stays within a reasonable chunk size.  Encoding is detected with a utf-8 →
gbk fallback, which covers the common cases of Chinese Excel exports.
"""

import csv
import io

from app.core.parser.base import BaseParser, BlockType, ParsedBlock

# Keep each emitted table block small enough to chunk cleanly.
MAX_ROWS_PER_BLOCK = 50


def _render_table(header: list[str], rows: list[list[str]]) -> str:
    """Render a header + rows as a markdown-style table."""
    def cell(value) -> str:
        text = "" if value is None else str(value)
        return text.replace("|", "\\|").replace("\n", " ").strip()

    lines = ["| " + " | ".join(cell(h) for h in header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        padded = list(row) + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(cell(v) for v in padded[:len(header)]) + " |")
    return "\n".join(lines)


def _read_csv_rows(file_path: str) -> list[list[str]]:
    """Read CSV rows with encoding fallback (utf-8 → gbk)."""
    raw = open(file_path, "rb").read()
    last_error = None
    for encoding in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
    else:
        raise ValueError(f"无法识别 CSV 编码: {last_error}")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows = []
    for line in reader:
        if any(str(cell).strip() for cell in line):
            rows.append([str(cell).strip() for cell in line])
    return rows


class CsvParser(BaseParser):
    """Parse CSV files into TABLE blocks."""

    def parse(self, file_path: str) -> list[ParsedBlock]:
        rows = _read_csv_rows(file_path)
        if not rows:
            return []

        header = rows[0]
        data_rows = rows[1:]

        blocks: list[ParsedBlock] = []
        for start in range(0, len(data_rows), MAX_ROWS_PER_BLOCK):
            group = data_rows[start:start + MAX_ROWS_PER_BLOCK]
            blocks.append(ParsedBlock(
                content=_render_table(header, group),
                block_type=BlockType.TABLE,
                metadata={
                    "rows": len(group),
                    "columns": len(header),
                    "row_start": start + 2,  # 1-based, header is row 1
                },
            ))
        return blocks
