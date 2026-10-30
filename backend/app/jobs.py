"""Single-worker GPU job queue that survives restarts.

One GPU, one job at a time. Every job is saved to DATA_DIR/jobs/<id>.json together with its request, so
after a power cut the server re-queues whatever was queued or running; handlers keep their own checkpoints
in `job.workdir` and pick up from there.
"""
import json
import logging
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from .config import settings

log = logging.getLogger("visionquery.jobs")

# Held by the worker for a whole job and by synchronous GPU endpoints (preview, suggestions, live).
gpu_lock = threading.Lock()


@dataclass
class Job:
    job_id: str
    kind: str
    video_id: str | None = None
    title: str = ""
    status: str = "queued"
    progress: float = 0.0
    message: str = "Waiting for the GPU…"
    result: Any = None
    error: str | None = None
    resumed: bool = False
    request: dict = field(default_factory=dict)
    version: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _saved_at: float = 0.0

    @property
    def workdir(self) -> Path:
        """Checkpoint folder for this job (created on demand)."""
        d = settings.jobs_dir / self.job_id
        d.mkdir(exist_ok=True)
        return d

    def update(self, **kw: Any) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)
            self.version += 1
        # Status changes are saved at once, progress at most once a second.
        if "status" in kw or "result" in kw or time.monotonic() - self._saved_at > 1.0:
            self.save()

    def to_dict(self) -> dict:
        with self._lock:
            result = self.result.model_dump() if hasattr(self.result, "model_dump") else self.result
            return {"job_id": self.job_id, "kind": self.kind, "video_id": self.video_id, "title": self.title,
                    "status": self.status, "progress": round(self.progress, 4), "message": self.message,
                    "result": result, "error": self.error, "resumed": self.resumed}

    def save(self) -> None:
        data = {**self.to_dict(), "request": self.request}
        tmp = settings.jobs_dir / f"{self.job_id}.json.tmp"
        try:
            tmp.write_text(json.dumps(data))
            tmp.replace(settings.jobs_dir / f"{self.job_id}.json")
            self._saved_at = time.monotonic()
        except OSError:
            log.warning("could not save job %s", self.job_id)

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error")


Handler = Callable[[Job, Any], Any]


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.handlers: dict[str, tuple[Handler, type[BaseModel]]] = {}
        self._queue: "queue.Queue[tuple[Job, BaseModel]]" = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="gpu-worker").start()

    def register(self, kind: str, fn: Handler, request_model: type[BaseModel]) -> None:
        self.handlers[kind] = (fn, request_model)

    def submit(self, kind: str, req: BaseModel, video_id: str | None = None, title: str = "") -> Job:
        job = Job(job_id=uuid.uuid4().hex[:12], kind=kind, video_id=video_id, title=title,
                  request=req.model_dump())
        self.jobs[job.job_id] = job
        job.save()
        self._queue.put((job, req))
        return job

    def get(self, job_id: str) -> Job | None:
        if job_id in self.jobs:
            return self.jobs[job_id]
        # A finished job from before a restart: serve it from disk.
        p = settings.jobs_dir / f"{job_id}.json"
        if job_id.isalnum() and p.exists():
            d = json.loads(p.read_text())
            d.pop("request", None)
            job = Job(**{k: v for k, v in d.items() if k in Job.__dataclass_fields__})
            self.jobs[job_id] = job
            return job
        return None

    def active(self) -> list[Job]:
        return [j for j in self.jobs.values() if not j.finished]

    def resume_unfinished(self) -> int:
        """Re-queue jobs that were queued or running when the server stopped (call after register())."""
        found = []
        for p in sorted(settings.jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                d = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if d.get("status") in ("queued", "running") and d.get("kind") in self.handlers:
                found.append(d)
        for d in found:
            _, model = self.handlers[d["kind"]]
            try:
                req = model.model_validate(d["request"])
            except Exception:
                continue
            job = Job(job_id=d["job_id"], kind=d["kind"], video_id=d.get("video_id"), title=d.get("title", ""),
                      progress=d.get("progress", 0.0), message="Resuming after restart…", resumed=True,
                      request=d["request"])
            self.jobs[job.job_id] = job
            job.save()
            self._queue.put((job, req))
        if found:
            log.info("resuming %d unfinished job(s)", len(found))
        return len(found)

    def _worker(self) -> None:
        while True:
            job, req = self._queue.get()
            fn, _ = self.handlers[job.kind]
            with gpu_lock:
                job.update(status="running", message="Resuming…" if job.resumed else "Starting…")
                try:
                    result = fn(job, req)
                    job.update(status="done", progress=1.0, result=result, message="Done")
                except Exception as e:  # surface every failure to the UI
                    log.error("job %s failed\n%s", job.job_id, traceback.format_exc())
                    job.update(status="error", error=str(e) or e.__class__.__name__, message="Failed")


jobs = JobManager()
