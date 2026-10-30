"""Per-video CLIP frame index: built once after upload, then every search is a dot product.

One frame every INDEX_STEP_SEC is embedded with CLIP (batches of INDEX_BATCH, float16 storage), so a
10-minute video is ~1,200 vectors (~1.2 MB). Instant search ranks those vectors against the query and runs
YOLO-World only on the best frames — most of the GPU work of a full scan disappears. The same index answers
image queries. Building is resumable: partial embeddings are saved after every batch.
"""
import json

import cv2
import numpy as np

from . import video
from .config import settings
from .jobs import Job
from .models import registry
from .schemas import IndexRequest, IndexStatus


def _paths(video_id: str):
    d = video.video_dir(video_id)
    return d / "index.npz", d / "index.json"


def step_for(fps: float) -> int:
    return max(1, round(fps * settings.index_step_sec))


def status(video_id: str) -> IndexStatus:
    npz, meta_p = _paths(video_id)
    meta = video.get_meta(video_id)
    if meta_p.exists():
        m = json.loads(meta_p.read_text())
        return IndexStatus(video_id=video_id, status="ready" if m.get("done") else "building",
                           frames_indexed=m.get("count", 0), step=m.get("step", step_for(meta.fps)))
    return IndexStatus(video_id=video_id, status="none", frames_indexed=0, step=step_for(meta.fps))


def load(video_id: str) -> tuple[np.ndarray, np.ndarray] | None:
    npz, meta_p = _paths(video_id)
    if not npz.exists() or not meta_p.exists() or not json.loads(meta_p.read_text()).get("done"):
        return None
    d = np.load(npz)
    return d["frames"], d["emb"].astype(np.float32)


def rank(video_id: str, query_vec: np.ndarray, top_k: int) -> list[tuple[int, float]]:
    """(frame_index, cosine similarity) of the best frames, best first; neighbours collapsed so the
    result covers different moments instead of 40 copies of the same second."""
    loaded = load(video_id)
    if loaded is None:
        return []
    frames, emb = loaded
    sims = emb @ query_vec.astype(np.float32)
    order = np.argsort(-sims)
    picked: list[tuple[int, float]] = []
    taken: set[int] = set()
    for i in order:
        if i in taken:
            continue
        picked.append((int(frames[i]), float(sims[i])))
        taken.update({i - 1, i, i + 1})  # skip direct neighbours (0.5 s apart)
        if len(picked) >= top_k:
            break
    return picked


def build(job: Job, req: IndexRequest) -> IndexStatus:
    meta = video.get_meta(req.video_id)
    npz, meta_p = _paths(req.video_id)
    step = step_for(meta.fps)
    wanted = list(range(0, meta.frame_count, step))

    frames: list[int] = []
    embs: list[np.ndarray] = []
    if npz.exists():  # resume after a restart
        d = np.load(npz)
        frames, embs = d["frames"].tolist(), [d["emb"]]
    done_set = set(frames)
    todo = [f for f in wanted if f not in done_set]

    job.update(message="Loading CLIP")
    clip = registry.use("clip")["clip"]
    cap = cv2.VideoCapture(str(video.source_path(req.video_id)))
    batch_idx: list[int] = []
    batch: list[np.ndarray] = []

    def flush() -> None:
        if not batch:
            return
        embs.append(clip.embed_images(batch))
        frames.extend(batch_idx)
        all_emb = np.concatenate(embs) if len(embs) > 1 else embs[0]
        embs.clear()
        embs.append(all_emb)
        np.savez(npz, frames=np.array(frames, np.int32), emb=all_emb)
        meta_p.write_text(json.dumps({"count": len(frames), "step": step, "done": False}))
        batch.clear()
        batch_idx.clear()
        job.update(progress=len(frames) / max(1, len(wanted)),
                   message=f"Indexed {len(frames):,}/{len(wanted):,} frames")

    try:
        idx = 0
        todo_set = set(todo)
        last = todo[-1] if todo else -1
        while idx <= last:
            if idx in todo_set:
                ok, frame = cap.read()
                if not ok:
                    break
                batch.append(cv2.cvtColor(video.resize_width(frame, 336), cv2.COLOR_BGR2RGB))
                batch_idx.append(idx)
                if len(batch) >= settings.index_batch:
                    flush()
            elif not cap.grab():
                break
            idx += 1
        flush()
    finally:
        cap.release()

    order = np.argsort(frames)
    all_emb = embs[0] if embs else np.zeros((0, 512), np.float16)
    np.savez(npz, frames=np.array(frames, np.int32)[order], emb=all_emb[order])
    meta_p.write_text(json.dumps({"count": len(frames), "step": step, "done": True}))

    # Search suggestions in the same GPU turn, so they never wait behind other jobs.
    from . import pipeline  # local import: pipeline imports this module

    job.update(progress=0.99, message="Finding objects for suggestions")
    pipeline.suggestions(req.video_id)
    return status(req.video_id)
