"""
HFusionHub Python AI Engine - FastAPI Application
"""

import os
import sys
import logging

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging — include trace_id from contextvars via LoggerAdapter
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Inject trace_id into every log record via a filter
class TraceFilter(logging.Filter):
    def filter(self, record):
        from app.utils.trace import get_trace_id
        record.trace_id = get_trace_id() or "-"
        return True

logging.getLogger().addFilter(TraceFilter())

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.utils.config import config
from app.api.vectorization import router as vectorization_router
from app.api.chat import router as chat_router
from app.api.rag import router as rag_router
from app.api.agent_observability_api import router as agent_obs_router
from app.api.mcp import router as mcp_router
from app.api.metrics import router as metrics_router
from app.api.runtime import router as runtime_router
from app.api.tools import router as tools_router
from app.api.plugin_admin import router as plugin_admin_router
from app.api.exception_handlers import (
    hfusionhub_exception_handler,
    http_exception_handler,
    general_exception_handler
)
from app.core.exceptions import HFusionHubException
from app.api.internal_auth import require_internal_token
from app.api.deps import require_tenant
from app.api.trace_middleware import TraceMiddleware
from app.api.tenant_middleware import TenantMiddleware

# Optional feature modules
try:
    from app.api.guardrails import router as guardrails_router
    _has_guardrails = True
except ImportError:
    _has_guardrails = False
    guardrails_router = None  # type: ignore

try:
    from app.api.gateway import router as gateway_router
    _has_gateway = True
except ImportError:
    _has_gateway = False
    gateway_router = None  # type: ignore


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

    # Distributed tracing — extract X-Trace-ID from upstream (Java) or generate fresh
    app.add_middleware(TraceMiddleware)

    # Tenant context — extract X-Tenant-Id from upstream (Java) or default to tenant 1
    app.add_middleware(TenantMiddleware)

    # Register exception handlers
    app.add_exception_handler(HFusionHubException, hfusionhub_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # Include routers
    # Every operational route is called by the Java application service.  Keep
    # only /health unauthenticated so infrastructure can probe availability.
    internal_dependencies = [Depends(require_internal_token)]
    # Data-touching routers require BOTH the internal token and an explicit,
    # verifiable tenant context (fail-closed — no default tenant).
    tenant_dependencies = [Depends(require_internal_token), Depends(require_tenant)]
    app.include_router(vectorization_router, dependencies=tenant_dependencies)
    app.include_router(chat_router, dependencies=tenant_dependencies)
    app.include_router(rag_router, dependencies=tenant_dependencies)
    # Applies on top of the internal token on the MCP data handler.
    app.include_router(agent_obs_router, dependencies=tenant_dependencies)
    # The MCP router keeps initialize/tools-list public for protocol discovery;
    # its tools/call handler separately enforces the internal token.
    app.include_router(mcp_router)
    # Metrics expose latency/error details; keep them on the internal network.
    app.include_router(metrics_router, dependencies=internal_dependencies)
    app.include_router(runtime_router, dependencies=internal_dependencies)
    app.include_router(tools_router, dependencies=tenant_dependencies)
    app.include_router(plugin_admin_router, dependencies=tenant_dependencies)

    # Optional feature modules
    if _has_gateway:
        app.include_router(gateway_router, dependencies=internal_dependencies)
    if _has_guardrails:
        app.include_router(guardrails_router, dependencies=internal_dependencies)

    @app.get("/")
    async def root():
        return {
            "service": "HFusionHub Python AI Engine",
            "version": "1.0.0",
            "status": "running"
        }

    @app.get("/health")
    async def health():
        # Liveness intentionally does not depend on Milvus; a transient vector
        # store outage must not cause Kubernetes to restart a healthy process.
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready():
        """Readiness endpoint used by the orchestrator and load balancers."""
        from app.core.vectorstore.milvus_store import vector_store_status
        vector_store = vector_store_status()
        payload = {"status": "ready" if vector_store["ready"] else "degraded",
                   "vector_store": vector_store}
        return JSONResponse(status_code=200 if vector_store["ready"] else 503,
                            content=payload)

    return app


app = create_app()


@app.on_event("startup")
async def startup_event() -> None:
    """Initialise subsystems that need async initialisation."""
    import os as _os

    # ── OpenTelemetry ─────────────────────────────────────────────────
    from app.utils.telemetry import init_telemetry
    init_telemetry(
        service_name="hfusionhub-python-ai",
        otlp_endpoint=_os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
        enabled=_os.environ.get("OTEL_ENABLED", "").lower() in ("1", "true", "yes"),
    )

    # ── MCP Client ────────────────────────────────────────────────────
    try:
        from app.core.tools.mcp_client import get_mcp_client_manager
        await get_mcp_client_manager().startup()
    except Exception:
        pass  # MCP is best-effort on startup

    # ── Model Gateway ─────────────────────────────────────────────────
    try:
        from app.core.llm.model_gateway import get_model_gateway
        gw = get_model_gateway()
        if gw.enabled:
            await gw.warmup()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Gracefully tear down background subsystems."""
    try:
        from app.core.tools.mcp_client import get_mcp_client_manager
        await get_mcp_client_manager().shutdown()
    except Exception:
        pass


def main():
    """Main entry point"""
    # Create upload directory
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    print(f"Starting HFusionHub Python AI Engine...")
    print(f"API documentation: http://{config.SERVER_HOST}:{config.SERVER_PORT}/docs")
    print(f"API host: {config.SERVER_HOST}, API port: {config.SERVER_PORT}")
    print(f"DeepSeek API: {config.DEEPSEEK_BASE_URL}")
    print(f"Milvus Lite: {config.MILVUS_LITE_PATH}")

    uvicorn.run(
        "app.main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=config.SERVER_DEBUG
    )


if __name__ == "__main__":
    main()
