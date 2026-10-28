import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline, video
from .config import settings
from .jobs import gpu_lock, jobs
from .models import DEVICE, registry, vram
from .schemas import Health, JobRef, PreviewRequest, RecolorRequest, SearchRequest, VideoMeta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="VisionQuery API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def _meta_or_404(video_id: str) -> VideoMeta:
    try:
        return video.get_meta(video_id)
    except FileNotFoundError:
        raise HTTPException(404, "Video not found")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    name, total, used = vram()
    return Health(device=DEVICE, gpu_name=name, vram_total_gb=total, vram_used_gb=used,
                  loaded_models=registry.loaded)


@app.post("/api/videos", response_model=VideoMeta)
def upload(file: UploadFile = File(...)) -> VideoMeta:
    if file.content_type and not file.content_type.startswith("video/"):
        raise HTTPException(415, "Please upload a video file")
    with tempfile.NamedTemporaryFile(delete=False, dir=settings.videos_dir, suffix=".upload") as tmp:
        shutil.copyfileobj(file.file, tmp, length=8 << 20)
    try:
        return video.ingest(Path(tmp.name), file.filename or "video.mp4")
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@app.get("/api/videos/{video_id}", response_model=VideoMeta)
def get_video(video_id: str) -> VideoMeta:
    return _meta_or_404(video_id)


@app.get("/api/videos/{video_id}/stream")
def stream(video_id: str) -> FileResponse:
    _meta_or_404(video_id)
    return FileResponse(video.source_path(video_id), media_type="video/mp4")


@app.get("/api/videos/{video_id}/frames/{index}.jpg")
def frame(video_id: str, index: int) -> FileResponse:
    meta = _meta_or_404(video_id)
    if not 0 <= index < meta.frame_count:
        raise HTTPException(404, "Frame out of range")
    try:
        path = video.thumbnail(video_id, index)
    except IndexError:
        raise HTTPException(404, "Frame not readable")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/search", response_model=JobRef)
def search(req: SearchRequest) -> JobRef:
    _meta_or_404(req.video_id)
    return JobRef(job_id=jobs.submit("search", pipeline.run_search, req).job_id)


@app.post("/api/recolor", response_model=JobRef)
def recolor(req: RecolorRequest) -> JobRef:
    _meta_or_404(req.video_id)
    return JobRef(job_id=jobs.submit("recolor", pipeline.run_recolor, req).job_id)


@app.post("/api/preview")
def preview(req: PreviewRequest) -> Response:
    _meta_or_404(req.video_id)
    if not gpu_lock.acquire(timeout=2):
        raise HTTPException(409, "The GPU is busy with another job — try again when it finishes")
    try:
        return Response(pipeline.preview(req), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except IndexError as e:
        raise HTTPException(404, str(e))
    finally:
        gpu_lock.release()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@app.websocket("/api/jobs/{job_id}/ws")
async def job_ws(ws: WebSocket, job_id: str) -> None:
    await ws.accept()
    job = jobs.get(job_id)
    if job is None:
        await ws.close(code=4404)
        return
    seen = -1
    try:
        while True:
            if job.version != seen:
                seen = job.version
                await ws.send_json(job.to_dict())
                if job.finished:
                    break
            await asyncio.sleep(0.25)
        await ws.close()
    except WebSocketDisconnect:
        pass


@app.get("/api/outputs/{job_id}.mp4")
def output(job_id: str) -> FileResponse:
    path = settings.outputs_dir / f"{job_id}.mp4"
    if not job_id.isalnum() or not path.exists():
        raise HTTPException(404, "Output not found")
    return FileResponse(path, media_type="video/mp4", filename=f"visionquery-{job_id}.mp4",
                        content_disposition_type="inline")


# Single-URL deployments (Colab, demos): serve the built React app from the same server.
# Mounted last so every /api route above wins.
_ui = os.getenv("FRONTEND_DIST")
if _ui and Path(_ui).is_dir():
    app.mount("/", StaticFiles(directory=_ui, html=True), name="ui")
