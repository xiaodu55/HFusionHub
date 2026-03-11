"""Agent observability REST endpoints.

Exposes agent-level operational metrics (latency, tokens, tool calls,
failure rates) and stale-run detection.  Follows the same internal-token
auth pattern as the other /api/* routers.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.agent.agent_observability import get_agent_trace_store

router = APIRouter(prefix="/api/agent/observability", tags=["Agent Observability"])


# ── Request models ─────────────────────────────────────────────────────

class AgentRunRecord(BaseModel):
    """Payload for explicitly recording a completed agent run trace."""
    run_uuid: str = Field(min_length=1, max_length=64)
    knowledge_base_id: Optional[int] = None
    status: str = Field(min_length=1, max_length=30)
    model: str = ""
    duration_ms: float = 0.0
    token_usage: Optional[Dict[str, int]] = None
    tool_calls_count: int = 0
    sources_count: int = 0
    step_count: int = 0
    approval_count: int = 0
    total_approval_duration_ms: float = 0.0
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    failed_tool: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/runs")
async def list_agent_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000),
    knowledge_base_id: Optional[int] = Query(default=None, ge=1),
    status: Optional[str] = Query(default=None, max_length=30),
    error_only: bool = Query(default=False),
):
    """List agent run traces with optional filters."""
    store = get_agent_trace_store()
    traces = store.list(
        limit=limit,
        offset=offset,
        knowledge_base_id=knowledge_base_id,
        status=status,
        error_only=error_only,
    )
    return {
        "traces": traces,
        "total": store.count(
            knowledge_base_id=knowledge_base_id,
            status=status,
            error_only=error_only,
        ),
    }


@router.get("/runs/{run_uuid}")
async def get_agent_run(run_uuid: str):
    """Get a single agent run trace by UUID."""
    store = get_agent_trace_store()
    trace = store.get(run_uuid)
    if trace is None:
        raise HTTPException(status_code=404, detail="Agent run trace not found")
    return trace


@router.get("/stats")
async def agent_stats(
    days: int = Query(default=7, ge=1, le=30),
    knowledge_base_id: Optional[int] = Query(default=None, ge=1),
):
    """Aggregated agent statistics for the given window."""
    return get_agent_trace_store().stats(
        window_days=days,
        knowledge_base_id=knowledge_base_id,
    )


@router.get("/stale-runs")
async def stale_runs(
    max_running_seconds: float = Query(default=120.0, ge=10.0, le=3600.0),
    knowledge_base_id: Optional[int] = Query(default=None, ge=1),
):
    """Detect runs stuck in 'running' state beyond the threshold."""
    runs = get_agent_trace_store().stale_runs(
        max_running_seconds=max_running_seconds,
        knowledge_base_id=knowledge_base_id,
    )
    return {
        "stale_runs": runs,
        "count": len(runs),
        "max_running_seconds": max_running_seconds,
    }


@router.post("/runs")
async def record_agent_run(run: AgentRunRecord):
    """Explicitly record an agent run trace from an external caller.

    The primary recording path is through ``SingleAgentWorkflow`` which
    calls ``AgentTraceStore.record()`` directly.  This endpoint allows
    the Java backend to push traces when it completes runs outside the
    workflow path (e.g. approval-resume flows).
    """
    from app.core.agent.agent_observability import AgentTrace

    store = get_agent_trace_store()
    trace = AgentTrace(
        run_uuid=run.run_uuid,
        knowledge_base_id=run.knowledge_base_id,
        status=run.status,
        model=run.model,
        duration_ms=run.duration_ms,
        token_usage=run.token_usage,
        tool_calls_count=run.tool_calls_count,
        sources_count=run.sources_count,
        step_count=run.step_count,
        approval_count=run.approval_count,
        total_approval_duration_ms=run.total_approval_duration_ms,
        error_code=run.error_code,
        error_detail=run.error_detail,
        failed_tool=run.failed_tool,
    )
    store.record(trace)
    return {"status": "recorded", "run_uuid": run.run_uuid}


# ── Agent Evaluation endpoints ──────────────────────────────────────────

class AgentEvalCaseRequest(BaseModel):
    """One evaluation case."""
    case_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=4000)
    answer: str = ""
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    ground_truth: Optional[str] = None
    expected_document_ids: List[str] = Field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    privilege_test: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[int] = None


class AgentEvalRunRequest(BaseModel):
    """Run a batch evaluation."""
    knowledge_base_id: Optional[int] = None
    user_id: Optional[int] = None
    label: Optional[str] = Field(default=None, max_length=120)
    agent_timeout_seconds: float = Field(
        default=20.0,
        ge=0.1,
        le=120.0,
        description="Per-case Agent execution budget. Timed-out cases are scored as failures, not batch errors.",
    )
    dimensions: List[str] = Field(
        default_factory=lambda: [
            "answer_correctness",
            "citation_consistency",
            "privilege_containment",
            "tool_success_rate",
        ]
    )
    cases: List[AgentEvalCaseRequest] = Field(min_length=1, max_length=200)


class RegressionCheckRequest(BaseModel):
    """Check the latest evaluation results against regression gates."""
    knowledge_base_id: Optional[int] = None
    thresholds: Optional[Dict[str, float]] = None


@router.post("/evaluate/run")
async def run_agent_evaluation(request: AgentEvalRunRequest):
    """Execute an offline agent answer evaluation on a batch of test cases.

    For each case, invokes the real Agent (SingleAgentWorkflow) to obtain
    actual answer, sources, and tool_calls.  The ground_truth /
    expected_document_ids fields are used *only* for scoring — they are
    NEVER substituted for the real agent output.
    """
    import asyncio
    import logging
    import uuid

    from app.core.agent import get_agent
    from app.core.agent.execution_context import AgentExecutionContext
    from app.core.agent.agent_evaluation import (
        AgentAnswerEvaluator,
        AgentEvalDimension,
        AgentEvalSample,
        AgentRegressionGate,
    )

    logger = logging.getLogger(__name__)

    # Parse dimensions
    dim_map = {d.value: d for d in AgentEvalDimension}
    dimensions = [
        dim_map[d] for d in request.dimensions
        if d in dim_map
    ]
    if not dimensions:
        dimensions = list(AgentEvalDimension)

    # Resolve per-case knowledge_base_id: case-level overrides top-level
    kb_id = request.knowledge_base_id
    eval_user_id = request.user_id or 0

    # ── Invoke real Agent for each case ───────────────────────────────
    samples: list = []
    agent_call_results: list = []  # per-case debug info for caseResults

    for c in request.cases:
        real_answer = c.answer
        real_sources = c.sources
        real_tool_calls = c.tool_calls
        agent_status = "skipped"
        agent_error = None

        case_kb_id = kb_id
        case_user_id = c.user_id or eval_user_id

        if case_kb_id and case_kb_id > 0 and c.query:
            try:
                exec_ctx = AgentExecutionContext(
                    user_id=case_user_id,
                    knowledge_base_id=case_kb_id,
                    permissions=frozenset({"knowledge_base:read"}),
                    agent_run_id=str(uuid.uuid4()),
                    mode="read_only",
                )
                agent = get_agent(
                    knowledge_base_id=case_kb_id,
                    execution_context=exec_ctx,
                )
                response = await asyncio.wait_for(
                    agent.run(query=c.query, history=[], style="concise", max_tool_steps=5),
                    timeout=request.agent_timeout_seconds,
                )
                real_answer = response.answer or response.content or ""
                real_sources = response.sources or []
                # Reconstruct tool_calls from AgentStep dataclass objects
                real_tool_calls = [
                    {"action": s.action, "status": "completed"}
                    for s in (response.steps or [])
                    if s.action
                ]
                if not real_tool_calls and response.tool_calls_count:
                    real_tool_calls = [{"action": "agent", "count": response.tool_calls_count}]
                agent_status = response.status or "completed"
            except asyncio.TimeoutError:
                agent_status = "timeout"
                agent_error = (
                    "Agent call timed out after "
                    f"{request.agent_timeout_seconds:g}s"
                )
                logger.warning("Evaluation agent timeout for case %s: %s", c.case_id, c.query[:80])
            except Exception as exc:
                agent_status = "error"
                agent_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                logger.warning("Evaluation agent error for case %s: %s", c.case_id, agent_error)

        # Record agent call result for debugging
        agent_call_results.append({
            "case_id": c.case_id,
            "query": c.query[:200],
            "real_answer": real_answer[:500] if real_answer else "",
            "real_sources_count": len(real_sources),
            "real_sources": [
                {"document_id": s.get("document_id", ""), "chunk_id": s.get("chunk_id", ""),
                 "excerpt": (s.get("excerpt", "") or "")[:100]}
                for s in (real_sources or [])[:5]
            ],
            "real_tool_calls_count": len(real_tool_calls),
            "agent_status": agent_status,
            "agent_error": agent_error,
        })

        samples.append(AgentEvalSample(
            case_id=c.case_id,
            query=c.query,
            answer=real_answer,
            sources=real_sources,
            ground_truth=c.ground_truth,
            expected_document_ids=c.expected_document_ids,
            tool_calls=real_tool_calls,
            privilege_test=c.privilege_test,
            metadata=c.metadata,
        ))

    # ── Run evaluation ────────────────────────────────────────────────
    evaluator = AgentAnswerEvaluator(dimensions=dimensions)
    run_id = str(uuid.uuid4())
    report = await evaluator.evaluate_batch(samples, run_id=run_id)

    # Merge per-case agent call info into the report cases
    enriched_cases = []
    for i, case_result in enumerate(report.cases):
        enriched = dict(case_result)
        if i < len(agent_call_results):
            enriched["agent_call"] = agent_call_results[i]
        enriched_cases.append(enriched)
    report.cases = enriched_cases

    # ── Run regression gate ──────────────────────────────────────────
    gate = AgentRegressionGate()
    gate_result = gate.check(report)

    return {
        **report.to_dict(),
        "regression_gate": gate_result.to_dict(),
        "label": request.label,
        "knowledge_base_id": request.knowledge_base_id,
    }


@router.post("/evaluate/regression-check")
async def check_regression(request: RegressionCheckRequest):
    """Run regression gate check using the latest stored evaluation data.

    This endpoint checks a pre-computed evaluation against quality thresholds.
    For a full evaluation + gate in one call, use POST /evaluate/run.
    """
    from app.core.agent.agent_evaluation import AgentRegressionGate

    gate = AgentRegressionGate(thresholds=request.thresholds)

    # Build a minimal report with passed-in thresholds
    return {
        "status": "ok",
        "message": "Pass thresholds in the /evaluate/run endpoint for a full report.",
        "default_thresholds": gate.thresholds,
    }
