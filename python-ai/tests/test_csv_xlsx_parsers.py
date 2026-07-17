"""
Tests for the CSV and XLSX table parsers (A3: 表格知识摄入).
"""

import csv
import zipfile

from app.core.parser.base import BaseParser, BlockType
from app.core.parser.csv_parser import CsvParser, _render_table
from app.core.parser.xlsx_parser import XlsxParser, _col_index, _col_name

# ── CSV ────────────────────────────────────────────────────────────────

def _write_csv(tmp_path, rows, encoding="utf-8-sig"):
    path = tmp_path / "sample.csv"
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    return str(path)


def test_csv_parser_produces_table_blocks(tmp_path):
    rows = [
        ["部门", "季度", "营收(万元)"],
        ["华东", "Q3", "34200"],
        ["华南", "Q3", "28700"],
    ]
    path = _write_csv(tmp_path, rows)

    blocks = CsvParser().parse(path)

    assert len(blocks) == 1
    block = blocks[0]
    assert block.block_type == BlockType.TABLE
    assert "部门" in block.content
    assert "Q3" in block.content
    assert block.metadata["rows"] == 2
    assert block.metadata["columns"] == 3


def test_csv_parser_groups_many_rows(tmp_path):
    header = ["id", "value"]
    rows = [header] + [[str(i), f"v{i}"] for i in range(120)]
    path = _write_csv(tmp_path, rows)

    blocks = CsvParser().parse(path)

    # 120 rows / 50 per block → 3 blocks
    assert len(blocks) == 3
    assert all(b.block_type == BlockType.TABLE for b in blocks)
    assert sum(b.metadata["rows"] for b in blocks) == 120


def test_csv_parser_gbk_encoding(tmp_path):
    rows = [["名称", "数量"], ["产品A", "10"]]
    path = _write_csv(tmp_path, rows, encoding="gbk")

    blocks = CsvParser().parse(path)

    assert len(blocks) == 1
    assert "产品A" in blocks[0].content


def test_csv_parser_registered_in_factory(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")

    parser = BaseParser.get_parser("csv")

    assert isinstance(parser, CsvParser)
    blocks = parser.parse(str(path))
    assert len(blocks) == 1


def test_render_table_escapes_pipes():
    rendered = _render_table(["col|A"], [["val|ue"]])
    assert "col\\|A" in rendered
    assert "val\\|ue" in rendered


# ── XLSX ───────────────────────────────────────────────────────────────

def _build_xlsx(tmp_path, sheets):
    """Build a minimal xlsx workbook in memory.

    sheets: list of (sheet_name, rows) where each row is a list of cell
    values.  Strings are emitted as shared strings; numbers as raw values.
    """
    path = tmp_path / "sample.xlsx"

    shared_items = []
    shared_lookup = {}

    def add_shared(text):
        if text not in shared_lookup:
            shared_lookup[text] = len(shared_items)
            shared_items.append(text)
        return shared_lookup[text]

    def sheet_xml(rows):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
               "<sheetData>"]
        for row in rows:
            out.append('<row r="1">')
            for col_idx, value in enumerate(row):
                ref = f"{_col_name(col_idx)}1"
                if isinstance(value, str):
                    out.append(f'<c r="{ref}" t="s"><v>{add_shared(value)}</v></c>')
                else:
                    out.append(f'<c r="{ref}"><v>{value}</v></c>')
            out.append("</row>")
        out.append("</sheetData></worksheet>")
        return "".join(out)

    with zipfile.ZipFile(path, "w") as zf:
        wb = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
        )
        wb_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        )
        for i, (name, rows) in enumerate(sheets, start=1):
            wb += (
                f'<sheet name="{name}" sheetId="{i}" '
                f'r:id="rId{i}"/>'
            )
            wb_rels += f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            zf.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(rows))
        wb += "</sheets></workbook>"
        wb_rels += "</Relationships>"
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        if shared_items:
            ss = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                f'count="{len(shared_items)}" uniqueCount="{len(shared_items)}">'
                + "".join(f"<si><t>{item}</t></si>" for item in shared_items)
                + "</sst>"
            )
            zf.writestr("xl/sharedStrings.xml", ss)
    return str(path)


def test_xlsx_parser_multiple_sheets(tmp_path):
    path = _build_xlsx(tmp_path, [
        ("财务", [["季度", "营收"], ["Q3", 34200], ["Q4", 41000]]),
        ("人员", [["姓名", "部门"], ["张三", "研发"]]),
    ])

    blocks = XlsxParser().parse(path)

    headings = [b for b in blocks if b.block_type == BlockType.HEADING]
    tables = [b for b in blocks if b.block_type == BlockType.TABLE]
    assert [h.content for h in headings] == ["财务", "人员"]
    assert len(tables) == 2
    assert "营收" in tables[0].content
    assert "34200" in tables[0].content
    assert "张三" in tables[1].content


def test_xlsx_parser_large_sheet_groups_rows(tmp_path):
    header = ["id", "name"]
    rows = [header] + [[i, f"item-{i}"] for i in range(120)]
    path = _build_xlsx(tmp_path, [("数据", rows)])

    blocks = XlsxParser().parse(path)

    tables = [b for b in blocks if b.block_type == BlockType.TABLE]
    assert len(tables) == 3
    assert sum(b.metadata["rows"] for b in tables) == 120


def test_xlsx_parser_registered_in_factory(tmp_path):
    path = _build_xlsx(tmp_path, [("表", [["a"], ["1"]])])

    parser = BaseParser.get_parser("xlsx")

    assert isinstance(parser, XlsxParser)
    assert len(parser.parse(str(path))) >= 1


def test_column_index_helpers():
    assert _col_index("A") == 0
    assert _col_index("B") == 1
    assert _col_index("Z") == 25
    assert _col_index("AA") == 26
    assert _col_name(0) == "A"
    assert _col_name(25) == "Z"
    assert _col_name(26) == "AA"
