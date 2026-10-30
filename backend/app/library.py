"""The local video library: everything the user uploaded, with the edits made from it.

Outputs are linked to their source video through the saved job files (jobs/<job_id>.json holds the video_id,
outputs/<job_id>.mp4 is the render), so deleting a video also removes its renders and checkpoints.
"""
import json
import shutil
from pathlib import Path

from . import index, video
from .config import settings
from .jobs import jobs
from .schemas import Library, LibraryItem


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _jobs_of(video_id: str) -> list[str]:
    ids = []
    for p in settings.jobs_dir.glob("*.json"):
        try:
            if json.loads(p.read_text()).get("video_id") == video_id:
                ids.append(p.stem)
        except (OSError, json.JSONDecodeError):
            continue
    return ids


def _busy(video_id: str) -> bool:
    return any(j.video_id == video_id for j in jobs.active())


def listing() -> Library:
    items: list[LibraryItem] = []
    total = 0
    for d in settings.videos_dir.iterdir():
        if not d.is_dir() or not (d / "meta.json").exists():
            continue
        try:
            meta = video.get_meta(d.name)
        except Exception:
            continue
        outputs = [settings.outputs_dir / f"{j}.mp4" for j in _jobs_of(d.name)]
        outputs = [o for o in outputs if o.exists()]
        size = _size(d) + sum(o.stat().st_size for o in outputs)
        total += size
        items.append(LibraryItem(
            meta=meta, created=(d / "meta.json").stat().st_mtime,
            thumbnail_url=f"/api/videos/{d.name}/frames/{meta.frame_count // 10}.jpg",
            index_status=index.status(d.name).status, outputs=len(outputs), bytes=size, busy=_busy(d.name)))
    items.sort(key=lambda i: i.created, reverse=True)
    return Library(path=str(settings.data_dir.resolve()), total_bytes=total, videos=items)


def delete(video_id: str) -> None:
    """Remove a video, its frames/index, its rendered edits and its job records."""
    if _busy(video_id):
        raise RuntimeError("A job is still running on this video")
    for job_id in _jobs_of(video_id):
        (settings.outputs_dir / f"{job_id}.mp4").unlink(missing_ok=True)
        (settings.jobs_dir / f"{job_id}.json").unlink(missing_ok=True)
        shutil.rmtree(settings.jobs_dir / job_id, ignore_errors=True)
        jobs.jobs.pop(job_id, None)
    shutil.rmtree(video.video_dir(video_id), ignore_errors=False)
