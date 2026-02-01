"""
PDF document parser
"""

from typing import List
from app.core.parser.base import BaseParser, ParsedBlock, BlockType


class PDFParser(BaseParser):
    """Parse PDF files into blocks"""

    def parse(self, file_path: str) -> List[ParsedBlock]:
        """Parse PDF file into blocks"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("PyPDF2 is required for PDF parsing. Install with: pip install PyPDF2")

        reader = PdfReader(file_path)
        blocks = []

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                # Split by paragraphs (double newlines)
                paragraphs = text.split('\n\n')

                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue

                    blocks.append(ParsedBlock(
                        content=para,
                        block_type=BlockType.PARAGRAPH,
                        metadata={
                            "page": page_num + 1,
                            "char_count": len(para)
                        }
                    ))

        return blocks
