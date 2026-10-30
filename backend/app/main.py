import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import (FastAPI, File, Form, HTTPException, Query, Response, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import commands, index, library, pipeline, video
from .arabic import translate
from .config import settings
from .jobs import gpu_lock, jobs
from .models import DEVICE, registry, vram
from .schemas import (CommandParse, CommandRequest, Health, ImageSearchRequest, IndexRequest, IndexStatus, JobRef,
                      Library, PreviewRequest, RecolorRequest, RedactRequest, SearchRequest, Suggestions, VideoMeta)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("visionquery")

app = FastAPI(title="VisionQuery API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

jobs.register("index", index.build, IndexRequest)
jobs.register("search", pipeline.run_search, SearchRequest)
jobs.register("image_search", pipeline.run_image_search, ImageSearchRequest)
jobs.register("recolor", pipeline.run_recolor, RecolorRequest)
jobs.register("redact", pipeline.run_redact, RedactRequest)
jobs.register("command", pipeline.run_command, CommandRequest)


@app.on_event("startup")
def resume_jobs() -> None:
    # Only unfinished jobs; old videos are indexed lazily when opened (see get_index), so a restart never
    # floods the GPU queue with work nobody asked for.
    jobs.resume_unfinished()


def _ensure_index(video_id: str) -> None:
    if index.status(video_id).status != "ready" and not any(
            j.kind == "index" and j.video_id == video_id for j in jobs.active()):
        jobs.submit("index", IndexRequest(video_id=video_id), video_id=video_id, title="Indexing video")


def _meta_or_404(video_id: str) -> VideoMeta:
    try:
        return video.get_meta(video_id)
    except FileNotFoundError:
        raise HTTPException(404, "Video not found")


def _gpu_or_409(timeout: float = 2) -> None:
    if not gpu_lock.acquire(timeout=timeout):
        raise HTTPException(409, "The GPU is busy with another job — try again when it finishes")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    name, total, used, cap = vram()
    return Health(device=DEVICE, gpu_name=name, vram_total_gb=total, vram_used_gb=used, vram_cap_gb=cap,
                  loaded_models=registry.loaded, busy=gpu_lock.locked())


@app.post("/api/videos", response_model=VideoMeta)
def upload(file: UploadFile = File(...)) -> VideoMeta:
    if file.content_type and not file.content_type.startswith("video/"):
        raise HTTPException(415, "Please upload a video file")
    with tempfile.NamedTemporaryFile(delete=False, dir=settings.videos_dir, suffix=".upload") as tmp:
        shutil.copyfileobj(file.file, tmp, length=8 << 20)
    try:
        meta = video.ingest(Path(tmp.name), file.filename or "video.mp4")
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    _ensure_index(meta.video_id)
    return meta


@app.get("/api/videos/{video_id}", response_model=VideoMeta)
def get_video(video_id: str) -> VideoMeta:
    return _meta_or_404(video_id)


@app.get("/api/library", response_model=Library)
def get_library() -> Library:
    return library.listing()


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str) -> dict:
    _meta_or_404(video_id)
    try:
        library.delete(video_id)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"deleted": video_id}


@app.get("/api/videos/{video_id}/stream")
def stream(video_id: str) -> FileResponse:
    _meta_or_404(video_id)
    return FileResponse(video.source_path(video_id), media_type="video/mp4")


@app.get("/api/videos/{video_id}/frames/{index_}.jpg")
def frame(video_id: str, index_: int) -> FileResponse:
    meta = _meta_or_404(video_id)
    if not 0 <= index_ < meta.frame_count:
        raise HTTPException(404, "Frame out of range")
    try:
        path = video.thumbnail(video_id, index_)
    except IndexError:
        raise HTTPException(404, "Frame not readable")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/videos/{video_id}/suggestions", response_model=Suggestions)
def get_suggestions(video_id: str) -> Suggestions:
    _meta_or_404(video_id)
    cache = video.video_dir(video_id) / "suggestions.json"
    if cache.exists():
        return Suggestions.model_validate_json(cache.read_text())
    # Normally produced by the index job. Compute now only if the GPU is free; otherwise 409 and the UI retries.
    _ensure_index(video_id)
    _gpu_or_409(timeout=1)
    try:
        return pipeline.suggestions(video_id)
    finally:
        gpu_lock.release()


@app.get("/api/videos/{video_id}/index", response_model=IndexStatus)
def get_index(video_id: str) -> IndexStatus:
    _meta_or_404(video_id)
    _ensure_index(video_id)  # older videos get their index (and suggestions) when first opened
    return index.status(video_id)


@app.get("/api/translate")
def get_translate(q: str = Query(..., max_length=200)) -> dict:
    en, translated = translate(q)
    return {"query_en": en, "translated": translated}


@app.get("/api/command/parse", response_model=CommandParse)
def parse_command(text: str = Query(..., max_length=300)) -> CommandParse:
    return commands.parse(text)


@app.post("/api/search", response_model=JobRef)
def search(req: SearchRequest) -> JobRef:
    _meta_or_404(req.video_id)
    return JobRef(job_id=jobs.submit("search", req, req.video_id, f"Searching “{req.query.strip()}”").job_id)


@app.post("/api/search-image", response_model=JobRef)
def search_image(video_id: str = Form(...), top_k: int = Form(40), file: UploadFile = File(...)) -> JobRef:
    _meta_or_404(video_id)
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "Please upload an image")
    data = file.file.read((10 << 20) + 1)
    if len(data) > 10 << 20:
        raise HTTPException(413, "Image larger than 10 MB")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(422, "Could not read the image")
    store = settings.jobs_dir / "images"
    store.mkdir(exist_ok=True)
    path = store / f"{os.urandom(6).hex()}.jpg"
    cv2.imwrite(str(path), video.resize_width(img, 640))
    req = ImageSearchRequest(video_id=video_id, image_path=str(path), top_k=max(5, min(top_k, 200)))
    return JobRef(job_id=jobs.submit("image_search", req, video_id, "Searching by image").job_id)


@app.post("/api/recolor", response_model=JobRef)
def recolor(req: RecolorRequest) -> JobRef:
    _meta_or_404(req.video_id)
    title = "Recoloring video" if len(req.targets) == 1 else f"Editing {len(req.targets)} objects"
    return JobRef(job_id=jobs.submit("recolor", req, req.video_id, title).job_id)


@app.post("/api/redact", response_model=JobRef)
def redact(req: RedactRequest) -> JobRef:
    _meta_or_404(req.video_id)
    return JobRef(job_id=jobs.submit("redact", req, req.video_id, f"Hiding every “{req.query.strip()}”").job_id)


@app.post("/api/command", response_model=JobRef)
def command(req: CommandRequest) -> JobRef:
    _meta_or_404(req.video_id)
    parsed = commands.parse(req.text)
    if not parsed.ok:
        raise HTTPException(422, parsed.error or "Could not understand the command")
    return JobRef(job_id=jobs.submit("command", req, req.video_id, f"“{req.text.strip()}”").job_id)


@app.post("/api/preview")
def preview(req: PreviewRequest) -> Response:
    _meta_or_404(req.video_id)
    _gpu_or_409()
    try:
        return Response(pipeline.preview(req), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except IndexError as e:
        raise HTTPException(404, str(e))
    finally:
        gpu_lock.release()


@app.get("/api/jobs")
def list_jobs(active: bool = False) -> list[dict]:
    items = jobs.active() if active else list(jobs.jobs.values())
    return [j.to_dict() for j in items]


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


# ---------------------------------------------------------------- live mode

_live_users = 0


def _live_detect(jpeg: bytes, query_en: str, conf: float) -> dict | None:
    """One webcam frame through YOLO-World, only if the GPU is free right now (never queues)."""
    if not gpu_lock.acquire(blocking=False):
        return None
    try:
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"w": 0, "h": 0, "ms": 0, "skipped": True, "query_en": query_en, "detections": []}
        t0 = time.perf_counter()
        yolo = registry.use("yolo_live")["yolo_live"]
        pipeline._set_classes(yolo, [query_en])
        res = yolo.predict(img, conf=conf, imgsz=480, device=DEVICE, verbose=False)[0]
        dets = [{"box": list(b), "score": round(s, 3), "label": query_en} for b, s, _ in pipeline._boxes(res)]
        h, w = img.shape[:2]
        return {"w": w, "h": h, "ms": round((time.perf_counter() - t0) * 1000), "skipped": False,
                "query_en": query_en, "detections": dets}
    finally:
        gpu_lock.release()


@app.websocket("/api/live")
async def live(ws: WebSocket, query: str = "person", conf: float = 0.25) -> None:
    """Detection only, at most LIVE_MAX_FPS frames per second, one viewer at a time; frames that arrive
    while the GPU is busy (or too soon) are answered with skipped=true. Effects are drawn by the browser."""
    global _live_users
    await ws.accept()
    if _live_users >= 1:
        await ws.send_json({"error": "Live mode is already open in another tab"})
        await ws.close()
        return
    _live_users += 1
    query_en = translate(query)[0].lower() or "person"
    conf = min(max(conf, 0.05), 0.9)
    min_gap = 1.0 / max(settings.live_max_fps, 0.5)
    last = 0.0
    try:
        while True:
            data = await ws.receive_bytes()
            now = time.monotonic()
            reply = None
            if now - last >= min_gap:
                reply = await run_in_threadpool(_live_detect, data, query_en, conf)
                if reply is not None and not reply["skipped"]:
                    last = now
            await ws.send_json(reply or {"w": 0, "h": 0, "ms": 0, "skipped": True, "query_en": query_en,
                                         "detections": []})
    except WebSocketDisconnect:
        pass
    finally:
        _live_users -= 1


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
