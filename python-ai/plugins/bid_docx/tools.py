"""bid_docx — 标书 docx 导出插件（HFusionHub 平台内建，容器沙箱执行）。

将已审批的标书分节草稿（bid_draft sections）渲染为 .docx 文档。
容器契约见 docker/plugin-runner/run_tool.py：工具名经 PLUGIN_TOOL_NAME 传入，
JSON 输入经 PLUGIN_TOOL_INPUT 传入，函数以关键字参数调用，返回值须 JSON 可序列化。

工具：bid_export_docx
  输入（JSON 对象）：
    - sections: [{key, title, content}]  标书分节（content 为分节长文）
    - title: str                          投标文件标题（默认 "投标文件"）
    - meta: {tender_number, project_title, company_name, bidder_name, deadline, budget}
 输出（JSON 对象）：
    - filename: str     建议文件名（含 .docx）
    - size_bytes: int   docx 字节数
    - chars: int        正文总字符数（供计量）
    - base64: str       docx 的 base64 编码（ASCII），调用方负责落盘/下发
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any, Dict, List, Optional

PLUGIN_VERSION = "1.0.0"
PLUGIN_NAME = "bid_docx"


def _iter_sections(sections: Any) -> List[Dict[str, Any]]:
    if isinstance(sections, str):
        try:
            sections = json.loads(sections)
        except json.JSONDecodeError:
            sections = []
    if not isinstance(sections, list):
        return []
    return [s for s in sections if isinstance(s, dict)]


def _normalize_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def bid_export_docx(
    sections: Any = None,
    title: str = "投标文件",
    meta: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """把标书分节草稿渲染为 .docx，返回 base64 字节与元信息。"""
    try:
        from docx import Document
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError as exc:  # pragma: no cover — 镜像内已安装
        raise RuntimeError(f"python-docx 未安装: {exc}") from exc

    title = _normalize_text(title) or "投标文件"
    meta = meta if isinstance(meta, dict) else {}
    sections = _iter_sections(sections)
    if not sections:
        raise ValueError("sections 必须是非空的分节数组 [{'key','title','content'}]")

    doc = Document()
    # 文档级默认字号
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)

    # ── 封面标题（居中）──
    heading = doc.add_heading(title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ── 元信息表（招标编号 / 项目名称 / 投标人 / 截止时间）──
    meta_items = [
        ("招标编号", meta.get("tender_number")),
        ("项目名称", meta.get("project_title")),
        ("投标人", meta.get("bidder_name")),
        ("投标截止", meta.get("deadline")),
        ("预算金额", meta.get("budget")),
    ]
    meta_rows = [(k, v) for k, v in meta_items if v not in (None, "")]
    if meta_rows:
        table = doc.add_table(rows=len(meta_rows), cols=2)
        table.style = "Light Grid Accent 1"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, (k, v) in enumerate(meta_rows):
            table.cell(i, 0).text = str(k)
            table.cell(i, 1).text = str(v)

    # ── 分节正文 ──
    total_chars = 0
    for sec in sections:
        sec_title = _normalize_text(sec.get("title")) or _normalize_text(sec.get("key")) or "分节"
        doc.add_heading(sec_title, level=1)
        content = _normalize_text(sec.get("content"))
        if not content:
            doc.add_paragraph("（本节为空）")
            continue
        total_chars += len(content)
        for block in content.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            p = doc.add_paragraph(block)
            # 常见标题行（# 开头）提为加粗
            if block.startswith("#"):
                p.text = block.lstrip("#").strip()
                p.runs and setattr(p.runs[0], "bold", True)

    # 页脚：平台免责声明
    footer = doc.sections[0].footer
    fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    fp.text = "本文件由 HFusionHub 招投标智能助手生成，仅供内部评审，发出前须经人工复核。"

    buf = io.BytesIO()
    doc.save(buf)
    raw = buf.getvalue()
    return {
        "filename": f"{title}.docx",
        "size_bytes": len(raw),
        "chars": total_chars,
        "base64": base64.b64encode(raw).decode("ascii"),
    }
