"""
Pipeline API endpoints — sector & individual pipelines with SSE streaming.
"""

import asyncio
import json
import math
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.services.pipeline_manager import PipelineManager
from backend.services.sector_pipeline import run_sector_pipeline
from backend.services.individual_pipeline import run_individual_pipeline
from backend.services.llm_service import check_api_status
from backend.services import prompts

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])
mgr = PipelineManager()


def _sanitize(obj):
    """Recursively replace NaN/Inf floats with None for JSON safety."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


# ── Request Models ──

class SectorStartRequest(BaseModel):
    url: str
    model_screener: str = "gemini"
    model_score: str = "gemini"
    sp_screener: Optional[str] = None
    sp_score: Optional[str] = None
    sp_json: Optional[str] = None


class IndividualStartRequest(BaseModel):
    url: str
    models: Optional[dict] = None
    custom_prompts: Optional[dict] = None


class IndividualStepRequest(BaseModel):
    run_id: str
    step: int
    url: Optional[str] = None
    models: Optional[dict] = None
    custom_prompts: Optional[dict] = None


# ── Sector Pipeline ──

@router.post("/sector/start")
async def start_sector_pipeline(req: SectorStartRequest, background_tasks: BackgroundTasks):
    """Start sector pipeline, return run_id."""
    run = mgr.create_run("sector")
    background_tasks.add_task(
        run_sector_pipeline,
        run.run_id,
        req.url,
        req.model_screener,
        req.model_score,
        req.sp_screener,
        req.sp_score,
        req.sp_json,
    )
    return {"run_id": run.run_id, "status": "started"}


# ── Individual Pipeline ──

@router.post("/individual/start")
async def start_individual_pipeline(req: IndividualStartRequest, background_tasks: BackgroundTasks):
    """Start full individual pipeline, return run_id."""
    run = mgr.create_run("individual")
    background_tasks.add_task(
        run_individual_pipeline,
        run.run_id,
        req.url,
        req.models,
        req.custom_prompts,
    )
    return {"run_id": run.run_id, "status": "started"}


@router.post("/individual/run-step")
async def run_individual_step(req: IndividualStepRequest, background_tasks: BackgroundTasks):
    """Run a single step of the individual pipeline."""
    run = mgr.get_run(req.run_id)
    if not run:
        # Create a new run for step-by-step mode
        run = mgr.create_run("individual")
        run.run_id = req.run_id if req.run_id else run.run_id

    # For step-by-step, reuse existing run
    actual_run = mgr.get_run(req.run_id)
    if not actual_run:
        actual_run = mgr.create_run("individual")

    background_tasks.add_task(
        run_individual_pipeline,
        actual_run.run_id,
        req.url or "",
        req.models,
        req.custom_prompts,
        step_only=req.step,
    )
    return {"run_id": actual_run.run_id, "status": "started", "step": req.step}


# ── SSE Stream ──

@router.get("/stream/{run_id}")
async def stream_pipeline(run_id: str):
    """SSE stream for real-time progress."""
    run = mgr.get_run(run_id)
    if not run:
        return {"error": "Run not found"}

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(run._event_queue.get(), timeout=30.0)
                data = json.dumps(_sanitize(event))
                yield f"event: {event['type']}\ndata: {data}\n\n"

                if event["type"] in ("done", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                # Send keepalive
                yield f": keepalive\n\n"

                # Check if run is finished
                if run.status in ("completed", "failed", "cancelled"):
                    final = {"type": "done", "data": {"message": f"Pipeline {run.status}"}}
                    yield f"event: done\ndata: {json.dumps(final)}\n\n"
                    break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Status & Control ──

@router.get("/status/{run_id}")
async def get_pipeline_status(run_id: str):
    """Poll current status of a pipeline run."""
    run = mgr.get_run(run_id)
    if not run:
        return {"error": "Run not found"}
    return JSONResponse(content=_sanitize({
        "run_id": run.run_id,
        "pipeline_type": run.pipeline_type,
        "status": run.status,
        "phase": run.phase,
        "total_phases": run.total_phases,
        "progress": run.progress,
        "progress_text": run.progress_text,
        "logs": run.logs,
        "results": run.results,
        "error": run.error,
        "created_at": run.created_at,
    }))


@router.post("/cancel/{run_id}")
async def cancel_pipeline(run_id: str):
    """Cancel a running pipeline."""
    success = mgr.cancel_run(run_id)
    if success:
        return {"status": "cancelled", "run_id": run_id}
    return {"error": "Run not found or not running"}


@router.get("/runs")
async def list_runs():
    """List all pipeline runs."""
    return JSONResponse(content=_sanitize({"runs": mgr.list_runs()}))


# ── API Status ──

@router.get("/api-status")
async def api_status():
    """Check API key connectivity for all models."""
    results = await asyncio.to_thread(check_api_status)
    return {"models": results}


# ── Default Prompts ──

@router.get("/prompts/sector/defaults")
async def sector_prompt_defaults():
    """Return default sector prompts."""
    return prompts.SECTOR_DEFAULTS


@router.get("/prompts/individual/defaults")
async def individual_prompt_defaults():
    """Return default individual prompts."""
    return prompts.INDIVIDUAL_DEFAULTS
