"""Single-worker job queue: one GPU, one job at a time; progress is polled by the WebSocket."""
import logging
import queue
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("visionquery.jobs")

# Held by the worker for a whole job and by synchronous GPU endpoints (preview).
gpu_lock = threading.Lock()


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Waiting for the GPU…"
    result: Any = None
    error: str | None = None
    version: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kw: Any) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)
            self.version += 1

    def to_dict(self) -> dict:
        with self._lock:
            result = self.result.model_dump() if hasattr(self.result, "model_dump") else self.result
            return {"job_id": self.job_id, "kind": self.kind, "status": self.status,
                    "progress": round(self.progress, 4), "message": self.message,
                    "result": result, "error": self.error}

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error")


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._queue: "queue.Queue[tuple[Job, Callable, tuple]]" = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="gpu-worker").start()

    def submit(self, kind: str, fn: Callable[..., Any], *args: Any) -> Job:
        job = Job(job_id=uuid.uuid4().hex[:12], kind=kind)
        self.jobs[job.job_id] = job
        self._queue.put((job, fn, args))
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def _worker(self) -> None:
        while True:
            job, fn, args = self._queue.get()
            with gpu_lock:
                job.update(status="running", message="Starting…")
                try:
                    result = fn(job, *args)
                    job.update(status="done", progress=1.0, result=result, message="Done")
                except Exception as e:  # surface every failure to the UI
                    log.error("job %s failed\n%s", job.job_id, traceback.format_exc())
                    job.update(status="error", error=str(e) or e.__class__.__name__, message="Failed")


jobs = JobManager()
