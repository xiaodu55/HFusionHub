"""
Markdown document parser
Supports: headings, paragraphs, code blocks, tables, lists
"""

import re

from app.core.parser.base import BaseParser, BlockType, ParsedBlock


class MarkdownParser(BaseParser):
    """Parse Markdown documents into blocks"""

    # Patterns for detecting block types
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    CODE_BLOCK_PATTERN = re.compile(r'^```(\w*)\n(.*?)^```', re.MULTILINE | re.DOTALL)
    TABLE_PATTERN = re.compile(r'^(\|.+\|)\n(\|[-|: ]+\|)\n((?:\|.+\|\n?)*)', re.MULTILINE)
    LIST_PATTERN = re.compile(r'^(\s*[-*+]\s+.+|\s*\d+\.\s+.+)$', re.MULTILINE)

    def parse(self, file_path: str) -> list[ParsedBlock]:
        """Parse Markdown file into blocks"""
        with open(file_path, encoding='utf-8') as f:
            content = f.read()

        return self._parse_content(content)

    def _parse_content(self, content: str) -> list[ParsedBlock]:
        """Parse markdown content into blocks"""
        blocks = []
        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # Check for code block
            if line.strip().startswith('```'):
                code_block, end_idx = self._extract_code_block(lines, i)
                if code_block:
                    blocks.append(code_block)
                    i = end_idx + 1
                    continue

            # Check for heading
            heading_match = self.HEADING_PATTERN.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                blocks.append(ParsedBlock(
                    content=text,
                    block_type=BlockType.HEADING,
                    level=level,
                    metadata={"raw": line}
                ))
                i += 1
                continue

            # Check for table
            if line.strip().startswith('|') and i + 2 < len(lines):
                table_block, end_idx = self._extract_table(lines, i)
                if table_block:
                    blocks.append(table_block)
                    i = end_idx + 1
                    continue

            # Check for list
            if self.LIST_PATTERN.match(line):
                list_block, end_idx = self._extract_list(lines, i)
                if list_block:
                    blocks.append(list_block)
                    i = end_idx + 1
                    continue

            # Default: paragraph
            paragraph, end_idx = self._extract_paragraph(lines, i)
            if paragraph:
                blocks.append(paragraph)
                i = end_idx + 1
                continue

            i += 1

        return blocks

    def _extract_code_block(self, lines: list[str], start: int) -> tuple:
        """Extract code block starting at given line"""
        if not lines[start].strip().startswith('```'):
            return None, start

        language = lines[start].strip()[3:].strip()
        code_lines = []
        i = start + 1

        while i < len(lines):
            if lines[i].strip().startswith('```'):
                content = '\n'.join(code_lines)
                return ParsedBlock(
                    content=content,
                    block_type=BlockType.CODE,
                    metadata={"language": language}
                ), i
            code_lines.append(lines[i])
            i += 1

        # Unclosed code block
        content = '\n'.join(code_lines)
        return ParsedBlock(
            content=content,
            block_type=BlockType.CODE,
            metadata={"language": language}
        ), i - 1

    def _extract_table(self, lines: list[str], start: int) -> tuple:
        """Extract table starting at given line"""
        if not lines[start].strip().startswith('|'):
            return None, start

        table_lines = []
        i = start

        while i < len(lines) and lines[i].strip().startswith('|'):
            table_lines.append(lines[i])
            i += 1

        if len(table_lines) < 2:
            return None, start

        content = '\n'.join(table_lines)
        return ParsedBlock(
            content=content,
            block_type=BlockType.TABLE,
            metadata={"rows": len(table_lines) - 1}  # Exclude header separator
        ), i - 1

    def _extract_list(self, lines: list[str], start: int) -> tuple:
        """Extract list starting at given line"""
        list_lines = []
        i = start

        while i < len(lines):
            line = lines[i]
            if not line.strip():
                # Empty line might end the list
                if i + 1 < len(lines) and self.LIST_PATTERN.match(lines[i + 1]):
                    list_lines.append(line)
                    i += 1
                    continue
                break
            if self.LIST_PATTERN.match(line):
                list_lines.append(line)
                i += 1
            else:
                break

        content = '\n'.join(list_lines)
        return ParsedBlock(
            content=content,
            block_type=BlockType.LIST,
            metadata={"items": len([line for line in list_lines if line.strip()])}
        ), i - 1

    def _extract_paragraph(self, lines: list[str], start: int) -> tuple:
        """Extract paragraph starting at given line"""
        paragraph_lines = []
        i = start

        while i < len(lines):
            line = lines[i]
            if not line.strip():
                break
            # Stop if we hit a special block
            if (line.strip().startswith('#') or
                line.strip().startswith('```') or
                line.strip().startswith('|') or
                self.LIST_PATTERN.match(line)):
                break
            paragraph_lines.append(line)
            i += 1

        if not paragraph_lines:
            return None, start

        content = '\n'.join(paragraph_lines)
        return ParsedBlock(
            content=content,
            block_type=BlockType.PARAGRAPH,
            metadata={"lines": len(paragraph_lines)}
        ), i - 1
