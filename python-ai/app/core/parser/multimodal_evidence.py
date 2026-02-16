"""Bounded, source-backed multimodal evidence extraction.

P8 deliberately turns tables and OCR text into normal ``ParsedBlock`` values
instead of creating a second image-vector index.  That keeps knowledge-base
scoping, citations, deletion and the existing hybrid retrieval trace on the
same proven path.  Image extraction and OCR are both opt-in best-effort
enrichments: a missing optional package, engine, malformed image or timeout
must never fail the document's text indexing job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Dict, Iterable, List, Optional, Tuple
from zipfile import BadZipFile, ZipFile

from app.core.parser.base import BlockType, ParsedBlock

logger = logging.getLogger(__name__)


@dataclass
class MultimodalEnrichmentReport:
    """A bounded summary safe to expose through task status and callbacks."""

    enabled: bool
    table_blocks: int = 0
    image_candidates: int = 0
    image_blocks: int = 0
    ocr_characters: int = 0
    skipped: Dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def to_dict(self) -> Dict[str, object]:
        return {
            "enabled": self.enabled,
            "table_blocks": self.table_blocks,
            "image_candidates": self.image_candidates,
            "image_blocks": self.image_blocks,
            "ocr_characters": self.ocr_characters,
            "skipped": dict(sorted(self.skipped.items())),
        }


class MultimodalEvidenceExtractor:
    """Extract OCR evidence from embedded PDF/DOCX images under strict limits."""

    _DOCX_MEDIA_PREFIX = "word/media/"
    _SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

    def __init__(
        self,
        *,
        enabled: bool,
        ocr_enabled: bool,
        ocr_command: str,
        ocr_language: str,
        max_images_per_document: int,
        max_image_bytes: int,
        max_ocr_characters: int,
        ocr_timeout_seconds: int,
    ) -> None:
        self.enabled = enabled
        self.ocr_enabled = ocr_enabled
        self.ocr_command = ocr_command
        self.ocr_language = ocr_language
        self.max_images_per_document = max(0, max_images_per_document)
        self.max_image_bytes = max(1, max_image_bytes)
        self.max_ocr_characters = max(1, max_ocr_characters)
        self.ocr_timeout_seconds = max(1, ocr_timeout_seconds)

    def enrich(self, file_path: str, file_type: str, blocks: List[ParsedBlock]) -> Tuple[List[ParsedBlock], MultimodalEnrichmentReport]:
        """Return original blocks plus source-backed table/image evidence.

        The method never mutates the parser output in-place.  It is safe to
        call before chunking and is intentionally synchronous, matching the
        existing parser API executed from the background indexing task.
        """
        report = MultimodalEnrichmentReport(enabled=self.enabled)
        if not self.enabled:
            return blocks, report

        enriched = [
            ParsedBlock(
                content=block.content,
                block_type=block.block_type,
                level=block.level,
                metadata=dict(block.metadata or {}),
            )
            for block in blocks
        ]
        for block in enriched:
            if block.block_type == BlockType.TABLE:
                block.metadata = {
                    **(block.metadata or {}),
                    "multimodal": {"kind": "table", "extraction": "native"},
                }
                report.table_blocks += 1

        normalized_type = (file_type or "").lower().lstrip(".")
        if not self.ocr_enabled:
            report.skip("ocr_disabled")
            return enriched, report
        if not self._ocr_available():
            report.skip("ocr_unavailable")
            return enriched, report

        try:
            images = self._extract_images(Path(file_path), normalized_type)
        except Exception as exc:  # parsing enrichment must never reject a document
            logger.warning("Multimodal image extraction skipped for %s: %s", file_path, exc)
            report.skip("image_extraction_failed")
            return enriched, report

        for position, (image_bytes, suffix, source_metadata) in enumerate(images, start=1):
            report.image_candidates += 1
            if position > self.max_images_per_document:
                report.skip("image_limit")
                break
            if len(image_bytes) > self.max_image_bytes:
                report.skip("image_too_large")
                continue
            if not image_bytes:
                report.skip("empty_image")
                continue
            ocr_text, reason = self._ocr(image_bytes, suffix)
            if not ocr_text:
                report.skip(reason or "ocr_empty")
                continue

            ocr_text = ocr_text[:self.max_ocr_characters]
            image_hash = sha256(image_bytes).hexdigest()
            enriched.append(ParsedBlock(
                content=f"[Image OCR]\n{ocr_text}",
                block_type=BlockType.IMAGE,
                metadata={
                    "multimodal": {
                        "kind": "image_ocr",
                        "image_sha256": image_hash,
                        "image_bytes": len(image_bytes),
                        "image_format": suffix.lstrip("."),
                        "ocr_engine": "tesseract",
                        "ocr_language": self.ocr_language,
                        **source_metadata,
                    },
                },
            ))
            report.image_blocks += 1
            report.ocr_characters += len(ocr_text)

        return enriched, report

    def _ocr_available(self) -> bool:
        command = self.ocr_command.strip()
        return bool(command and (os.path.isabs(command) and os.path.isfile(command) or shutil.which(command)))

    def _extract_images(self, file_path: Path, file_type: str) -> Iterable[Tuple[bytes, str, Dict[str, object]]]:
        if file_type == "docx":
            return self._extract_docx_images(file_path)
        if file_type == "pdf":
            return self._extract_pdf_images(file_path)
        return []

    def _extract_docx_images(self, file_path: Path) -> Iterable[Tuple[bytes, str, Dict[str, object]]]:
        try:
            with ZipFile(file_path) as archive:
                images = []
                for name in sorted(archive.namelist()):
                    if not name.startswith(self._DOCX_MEDIA_PREFIX) or name.endswith("/"):
                        continue
                    suffix = Path(name).suffix.lower()
                    if suffix not in self._SUPPORTED_IMAGE_SUFFIXES:
                        continue
                    images.append((archive.read(name), suffix, {
                        "source_file_type": "docx",
                        "image_part": name,
                    }))
                return images
        except (BadZipFile, OSError) as exc:
            raise ValueError("invalid DOCX image archive") from exc

    def _extract_pdf_images(self, file_path: Path) -> Iterable[Tuple[bytes, str, Dict[str, object]]]:
        """Use optional pypdf's documented ``page.images`` API.

        PyPDF2 remains the text parser used by the service.  ``pypdf`` is only
        an explicit P8 optional dependency because robust image extraction is
        version-sensitive and should not change the baseline parser package.
        """
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf not installed") from exc

        reader = PdfReader(str(file_path))
        images = []
        for page_number, page in enumerate(reader.pages, start=1):
            for image_number, image in enumerate(page.images, start=1):
                name = getattr(image, "name", "")
                suffix = Path(name).suffix.lower() or ".png"
                if suffix not in self._SUPPORTED_IMAGE_SUFFIXES:
                    continue
                images.append((image.data, suffix, {
                    "source_file_type": "pdf",
                    "page_number": page_number,
                    "image_number": image_number,
                }))
        return images

    def _ocr(self, image_bytes: bytes, suffix: str) -> Tuple[str, Optional[str]]:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(image_bytes)
                temp_path = handle.name
            completed = subprocess.run(
                [self.ocr_command, temp_path, "stdout", "-l", self.ocr_language, "--psm", "6"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.ocr_timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
            if completed.returncode != 0:
                logger.info("Tesseract returned %s: %s", completed.returncode, completed.stderr[:300])
                return "", "ocr_failed"
            text = completed.stdout.strip()
            return text, None if text else "ocr_empty"
        except subprocess.TimeoutExpired:
            return "", "ocr_timeout"
        except OSError as exc:
            logger.warning("Tesseract execution failed: %s", exc)
            return "", "ocr_failed"
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
