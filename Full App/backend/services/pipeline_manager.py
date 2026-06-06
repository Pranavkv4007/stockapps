"""
In-memory pipeline state management.
Tracks pipeline runs, progress, logs, and SSE event queues.
"""

import uuid
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PipelineRun:
    run_id: str
    pipeline_type: str  # "sector" or "individual"
    status: str = "pending"  # pending, running, completed, failed, cancelled, awaiting_cache_decision
    phase: int = -1
    total_phases: int = 8
    progress: float = 0.0
    progress_text: str = ""
    logs: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    _event_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue())
    _cancelled: bool = False
    _cache_event: asyncio.Event = field(default_factory=lambda: asyncio.Event())
    cache_decision: Optional[str] = None  # "continue" | "delete"

    def is_cancelled(self):
        return self._cancelled


class PipelineManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._runs = {}
        return cls._instance

    def create_run(self, pipeline_type: str) -> PipelineRun:
        run_id = str(uuid.uuid4())[:8]
        run = PipelineRun(run_id=run_id, pipeline_type=pipeline_type)
        self._runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        return self._runs.get(run_id)

    def cancel_run(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run and run.status in ("running", "awaiting_cache_decision"):
            run._cancelled = True
            run.status = "cancelled"
            run._cache_event.set()  # unblock any waiting coroutine
            self.push_event(run_id, "cancelled", {"message": "Pipeline cancelled by user"})
            return True
        return False

    def set_cache_decision(self, run_id: str, decision: str) -> bool:
        run = self._runs.get(run_id)
        if run and run.status == "awaiting_cache_decision":
            run.cache_decision = decision
            run.status = "running"
            run._cache_event.set()
            return True
        return False

    def list_runs(self):
        return [
            {
                "run_id": r.run_id,
                "pipeline_type": r.pipeline_type,
                "status": r.status,
                "phase": r.phase,
                "progress": r.progress,
                "created_at": r.created_at,
                "error": r.error,
            }
            for r in self._runs.values()
        ]

    def push_event(self, run_id: str, event_type: str, data: dict):
        run = self._runs.get(run_id)
        if run:
            event = {"type": event_type, "data": data, "timestamp": datetime.now().isoformat()}
            try:
                run._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def add_log(self, run_id: str, message: str):
        run = self._runs.get(run_id)
        if run:
            ts = datetime.now().strftime("%H:%M:%S")
            entry = f"[{ts}] {message}"
            run.logs.append(entry)
            self.push_event(run_id, "log", {"message": entry})
