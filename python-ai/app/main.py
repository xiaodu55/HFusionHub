"""
HFusionHub Python AI Engine - FastAPI Application
"""

import os
import sys
import logging

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging so background task logs are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.utils.config import config
from app.api.vectorization import router as vectorization_router
from app.api.chat import router as chat_router
from app.api.rag import router as rag_router
from app.api.exception_handlers import (
    hfusionhub_exception_handler,
    http_exception_handler,
    general_exception_handler
)
from app.core.exceptions import HFusionHubException
from app.api.internal_auth import require_internal_token


def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title="HFusionHub Python AI Engine",
        description="Document vectorization and RAG processing service",
        version="1.0.0"
    )

    # Browsers reject credentialed requests with a wildcard origin. Keep the
    # development defaults explicit and make production origins configurable.
    allow_all_origins = config.CORS_ORIGINS == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=not allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    app.add_exception_handler(HFusionHubException, hfusionhub_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # Include routers
    # Every operational route is called by the Java application service.  Keep
    # only /health unauthenticated so infrastructure can probe availability.
    internal_dependencies = [Depends(require_internal_token)]
    app.include_router(vectorization_router, dependencies=internal_dependencies)
    app.include_router(chat_router, dependencies=internal_dependencies)
    app.include_router(rag_router, dependencies=internal_dependencies)

    @app.get("/")
    async def root():
        return {
            "service": "HFusionHub Python AI Engine",
            "version": "1.0.0",
            "status": "running"
        }

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()


def main():
    """Main entry point"""
    # Create upload directory
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    print(f"Starting HFusionHub Python AI Engine...")
    print(f"API documentation: http://{config.SERVER_HOST}:{config.SERVER_PORT}/docs")
    print(f"API host: {config.SERVER_HOST}, API port: {config.SERVER_PORT}")
    print(f"DeepSeek API: {config.DEEPSEEK_BASE_URL}")
    print(f"Milvus: {config.MILVUS_HOST}:{config.MILVUS_PORT}")

    uvicorn.run(
        "app.main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=config.SERVER_DEBUG
    )


if __name__ == "__main__":
    main()
