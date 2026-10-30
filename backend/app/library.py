"""The local video library: everything the user uploaded, with the edits made from it.

Outputs are linked to their source video through the saved job files (jobs/<job_id>.json holds the video_id,
outputs/<job_id>.mp4 is the render), so deleting a video also removes its renders and checkpoints.

On Windows a file that is still being streamed to the browser cannot be deleted, so deletion first removes
meta.json (the video disappears from the library at once) and then removes the files in the background,
retrying until the player lets go. Folders left half-deleted (no meta.json) are swept at startup.
"""
import json
import logging
import shutil
import threading
import time
from pathlib import Path

from . import index, video
from .config import settings
from .jobs import jobs
from .schemas import Library, LibraryItem

log = logging.getLogger("visionquery.library")


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


def _remove(path: Path, attempts: int = 60, wait: float = 2.0) -> None:
    """Delete a file or folder, retrying while Windows reports it in use (e.g. still streaming)."""
    for _ in range(attempts):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(wait)
    log.warning("could not delete %s (still in use)", path)


def _remove_later(*paths: Path) -> None:
    threading.Thread(target=lambda: [_remove(p) for p in paths], daemon=True).start()


def delete(video_id: str) -> None:
    """Remove a video, its frames/index, its rendered edits and its job records."""
    if _busy(video_id):
        raise RuntimeError("A job is still running on this video")
    d = video.video_dir(video_id)
    (d / "meta.json").unlink(missing_ok=True)  # gone from the library and the API right away
    later: list[Path] = [d]
    for job_id in _jobs_of(video_id):
        jobs.jobs.pop(job_id, None)
        later += [settings.outputs_dir / f"{job_id}.mp4", settings.jobs_dir / f"{job_id}.json",
                  settings.jobs_dir / job_id]
    _remove_later(*later)


def sweep() -> int:
    """Finish deletions interrupted by a locked file or a restart: folders without meta.json."""
    leftovers = [d for d in settings.videos_dir.iterdir() if d.is_dir() and not (d / "meta.json").exists()]
    if leftovers:
        _remove_later(*leftovers)
    return len(leftovers)
