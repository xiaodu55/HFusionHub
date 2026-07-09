"""Image parser — 独立图片文件（png/jpg/jpeg）的 OCR 入库路线。

复用既有 `MultimodalEvidenceExtractor` 的 Tesseract OCR 通道（``_ocr``），
不引入 vision-LLM 依赖，也不新增第三方包：

- ``RAG_MULTIMODAL_OCR_ENABLED=true`` → OCR 文本作为 PARAGRAPH 块输出，
  走同一检索/引用/删除管道；
- 关闭时抛 ``ValueError``（Java 侧 ParsingException 语义：明确提示先开启 OCR），
  避免静默入库一张"看起来解析成功"的空文档。

OCR 是子进程调用（CPU/IO 密集），上游 vectorization 已把 parse 放进
``asyncio.to_thread``，这里保持同步实现即可。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from app.core.parser.base import BaseParser, BlockType, ParsedBlock

logger = logging.getLogger(__name__)

_SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg"}
# 单图 OCR 文本上限与 RAG_MULTIMODAL_MAX_OCR_CHARACTERS 默认值一致
_MAX_OCR_CHARACTERS = 3000


class ImageParser(BaseParser):
    """OCR a standalone image file into a single text block."""

    def parse(self, file_path: str) -> List[ParsedBlock]:
        from app.utils.config import config

        if not config.RAG_MULTIMODAL_OCR_ENABLED:
            raise ValueError(
                "图片文件解析需要 OCR 支持：请安装 Tesseract 并设置 "
                "RAG_MULTIMODAL_OCR_ENABLED=true（当前为关闭）"
            )

        suffix = Path(file_path).suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported image type: {suffix}")

        from app.core.parser.multimodal_evidence import MultimodalEvidenceExtractor

        extractor = MultimodalEvidenceExtractor(
            enabled=True,
            ocr_enabled=True,
            ocr_command=config.RAG_MULTIMODAL_OCR_COMMAND,
            ocr_language=config.RAG_MULTIMODAL_OCR_LANGUAGE,
            max_images_per_document=1,
            max_image_bytes=config.RAG_MULTIMODAL_MAX_IMAGE_BYTES,
            max_ocr_characters=config.RAG_MULTIMODAL_MAX_OCR_CHARACTERS,
            ocr_timeout_seconds=config.RAG_MULTIMODAL_OCR_TIMEOUT_SECONDS,
        )
        image_bytes = Path(file_path).read_bytes()
        if len(image_bytes) > config.RAG_MULTIMODAL_MAX_IMAGE_BYTES:
            raise ValueError(
                f"图片超过大小上限（{len(image_bytes)} > "
                f"{config.RAG_MULTIMODAL_MAX_IMAGE_BYTES} 字节）"
            )

        text, error = extractor._ocr(image_bytes, suffix)
        if error or not text:
            logger.info("Image OCR failed for %s: %s", file_path, error)
            raise ValueError(f"图片 OCR 未提取到文本（{error or 'empty'}）")

        text = text[:_MAX_OCR_CHARACTERS]
        return [ParsedBlock(
            content=text,
            block_type=BlockType.PARAGRAPH,
            metadata={"source": "image_ocr"},
        )]


__all__ = ["ImageParser"]
