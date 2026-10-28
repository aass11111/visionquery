"""Video storage, metadata, frame access and H.264 encoding."""
import shutil
import subprocess
import uuid
from pathlib import Path

import cv2
import numpy as np

from .config import settings
from .schemas import VideoMeta

BROWSER_CODECS = {"h264", "vp8", "vp9", "av1"}


def video_dir(video_id: str) -> Path:
    if not video_id.isalnum():
        raise FileNotFoundError(video_id)
    return settings.videos_dir / video_id


def source_path(video_id: str) -> Path:
    d = video_dir(video_id)
    for p in d.glob("source.*"):
        return p
    raise FileNotFoundError(video_id)


def get_meta(video_id: str) -> VideoMeta:
    p = video_dir(video_id) / "meta.json"
    if not p.exists():
        raise FileNotFoundError(video_id)
    return VideoMeta.model_validate_json(p.read_text())


def _probe_codec(path: Path) -> str | None:
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    return out.stdout.strip() or None


def ingest(upload_path: Path, filename: str) -> VideoMeta:
    """Move an uploaded file into storage, transcode to H.264 if a browser could not play it, read metadata."""
    video_id = uuid.uuid4().hex[:12]
    d = video_dir(video_id)
    d.mkdir(parents=True)
    ext = Path(filename).suffix.lower() or ".mp4"
    src = d / f"source{ext}"
    shutil.move(str(upload_path), src)

    codec = _probe_codec(src)
    if codec is not None and (codec not in BROWSER_CODECS or ext not in {".mp4", ".webm", ".m4v"}):
        dst = d / "source_h264.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "20", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
             "-c:a", "aac", "-movflags", "+faststart", str(dst)],
            check=True,
        )
        src.unlink()
        src = dst.rename(d / "source.mp4")

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        shutil.rmtree(d, ignore_errors=True)
        raise ValueError("Could not decode this video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if frames <= 0 or w <= 0:
        shutil.rmtree(d, ignore_errors=True)
        raise ValueError("Video has no readable frames")

    meta = VideoMeta(video_id=video_id, filename=filename, fps=round(fps, 3), frame_count=frames,
                     width=w, height=h, duration=round(frames / fps, 3))
    (d / "meta.json").write_text(meta.model_dump_json())
    return meta


def read_frame(video_id: str, index: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(source_path(video_id)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise IndexError(f"frame {index} not readable")
    return frame


def resize_width(frame: np.ndarray, width: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    return cv2.resize(frame, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)


def encode_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", resize_width(frame, settings.thumb_width), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def thumbnail_path(video_id: str, index: int) -> Path:
    return video_dir(video_id) / "frames" / f"{index}.jpg"


def save_thumbnail(video_id: str, index: int, frame: np.ndarray) -> str:
    p = thumbnail_path(video_id, index)
    p.parent.mkdir(exist_ok=True)
    if not p.exists():
        p.write_bytes(encode_jpeg(frame))
    return f"/api/videos/{video_id}/frames/{index}.jpg"


def thumbnail(video_id: str, index: int) -> Path:
    p = thumbnail_path(video_id, index)
    if not p.exists():
        save_thumbnail(video_id, index, read_frame(video_id, index))
    return p


class H264Writer:
    """Pipes raw BGR frames into ffmpeg; copies the source audio track when there is one."""

    def __init__(self, out_path: Path, width: int, height: int, fps: float, audio_from: Path | None = None):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{width}x{height}", "-r", f"{fps}", "-i", "-"]
        if audio_from is not None:
            cmd += ["-i", str(audio_from), "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-movflags", "+faststart", str(out_path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode() if self.proc.stderr else ""
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err.strip()[-400:]}")
