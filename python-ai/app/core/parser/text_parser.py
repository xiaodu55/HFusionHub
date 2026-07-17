"""
Plain text document parser
"""


from app.core.parser.base import BaseParser, BlockType, ParsedBlock


class TextParser(BaseParser):
    """Parse plain text files into blocks"""

    def parse(self, file_path: str) -> list[ParsedBlock]:
        """Parse text file into blocks (paragraphs separated by empty lines)"""
        with open(file_path, encoding='utf-8') as f:
            content = f.read()

        return self._parse_content(content)

    def _parse_content(self, content: str) -> list[ParsedBlock]:
        """Parse text content into paragraph blocks"""
        blocks = []
        paragraphs = content.split('\n\n')

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            blocks.append(ParsedBlock(
                content=para,
                block_type=BlockType.PARAGRAPH,
                metadata={"char_count": len(para)}
            ))

        # If no paragraphs found (no double newline), treat entire content as one block
        if not blocks and content.strip():
            blocks.append(ParsedBlock(
                content=content.strip(),
                block_type=BlockType.PARAGRAPH,
                metadata={"char_count": len(content.strip())}
            ))

        return blocks
