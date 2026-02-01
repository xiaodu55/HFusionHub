"""
Base parser class for document parsing
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class BlockType(Enum):
    """Block type enumeration"""
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    CODE = "CODE"
    TABLE = "TABLE"
    LIST = "LIST"
    IMAGE = "IMAGE"


@dataclass
class ParsedBlock:
    """Parsed block from document"""
    content: str
    block_type: BlockType
    level: Optional[int] = None  # For headings: 1, 2, 3...
    metadata: Optional[dict] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseParser(ABC):
    """Base class for document parsers"""

    @abstractmethod
    def parse(self, file_path: str) -> List[ParsedBlock]:
        """
        Parse document and return list of blocks

        Args:
            file_path: Path to the document file

        Returns:
            List of ParsedBlock objects
        """
        pass

    @staticmethod
    def get_parser(file_type: str) -> 'BaseParser':
        """
        Factory method to get appropriate parser

        Args:
            file_type: File extension (md, txt, pdf, docx)

        Returns:
            Parser instance
        """
        from app.core.parser.markdown_parser import MarkdownParser
        from app.core.parser.text_parser import TextParser
        from app.core.parser.pdf_parser import PDFParser
        from app.core.parser.docx_parser import DocxParser

        parsers = {
            "md": MarkdownParser,
            "markdown": MarkdownParser,
            "txt": TextParser,
            "text": TextParser,
            "pdf": PDFParser,
            "docx": DocxParser,
        }

        parser_class = parsers.get(file_type.lower())
        if parser_class is None:
            raise ValueError(f"Unsupported file type: {file_type}")

        return parser_class()
