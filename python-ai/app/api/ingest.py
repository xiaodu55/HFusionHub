"""
Ingestion API routes — URL-based knowledge ingestion.

``POST /api/ingest/url`` fetches a public HTTPS webpage (SSRF-guarded),
extracts readable text and writes it into the shared document storage root
as markdown, so the normal Java → parse pipeline can index it unchanged.
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.exceptions import ParsingException
from app.core.ingest.url_fetcher import fetch_and_extract
from app.utils.config import config

router = APIRouter()
logger = logging.getLogger(__name__)


class UrlIngestRequest(BaseModel):
    url: str = Field(..., description="公开 HTTPS 网页地址")
    title: str | None = Field(None, description="可选标题覆盖（默认取自网页 <title>）")


class UrlIngestResponse(BaseModel):
    success: bool
    file_path: str
    file_type: str = "md"
    title: str
    content_length: int
    message: str


@router.post("/api/ingest/url", response_model=UrlIngestResponse)
async def ingest_url(request: UrlIngestRequest):
    """Fetch a webpage and stage it as a markdown document for indexing."""
    try:
        title, text = await fetch_and_extract(request.url)
    except ValueError as exc:
        raise ParsingException(message=str(exc)) from exc
    except Exception as exc:  # httpx transport errors and friends
        logger.warning("[ingest/url] fetch failed: %s", exc)
        raise ParsingException(message="网页抓取失败，请稍后重试") from exc

    if not text.strip():
        raise ParsingException(message="该网页没有可提取的正文内容")

    storage_root = Path(config.DOCUMENT_STORAGE_ROOT).expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.md"
    file_path = storage_root / filename

    effective_title = (request.title or title or request.url).strip()[:200]
    content = f"# {effective_title}\n\n来源: {request.url}\n\n{text.strip()}\n"
    file_path.write_text(content, encoding="utf-8")

    logger.info("[ingest/url] staged %s (%d chars) for %s", file_path, len(content), request.url)
    return UrlIngestResponse(
        success=True,
        file_path=str(file_path),
        title=effective_title,
        content_length=len(content),
        message="网页已抓取并暂存，等待解析",
    )
