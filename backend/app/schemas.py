"""Pydantic mirror of frontend/src/types.ts."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Box = tuple[float, float, float, float]


class VideoMeta(BaseModel):
    video_id: str
    filename: str
    fps: float
    frame_count: int
    width: int
    height: int
    duration: float


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    device: Literal["cuda", "cpu"]
    gpu_name: Optional[str]
    vram_total_gb: Optional[float]
    vram_used_gb: Optional[float]
    loaded_models: list[str]


class Detection(BaseModel):
    box: Box
    score: float
    det_score: float
    clip_score: Optional[float]
    label: str


class FrameHit(BaseModel):
    frame_index: int
    time: float
    thumbnail_url: str
    detections: list[Detection]
    best_score: float


class SearchResult(BaseModel):
    query: str
    frame_step: int
    frames_scanned: int
    hits: list[FrameHit]


class RecolorResult(BaseModel):
    output_url: str
    frames_written: int
    frames_segmented: int


def _hex(v: str) -> str:
    v = v.strip()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) != 7 or any(c not in "0123456789abcdefABCDEF" for c in v[1:]):
        raise ValueError("color must be #RRGGBB")
    return v.lower()


class SearchRequest(BaseModel):
    video_id: str
    query: str = Field(min_length=1, max_length=200)
    frame_step: int = Field(5, ge=1, le=120)
    conf: float = Field(0.15, ge=0.01, le=0.95)
    use_clip: bool = True


class PreviewRequest(BaseModel):
    video_id: str
    frame_index: int = Field(ge=0)
    box: Box
    color: str
    strength: float = Field(0.85, ge=0, le=1)

    @field_validator("color")
    @classmethod
    def check_color(cls, v: str) -> str:
        return _hex(v)


class RecolorRequest(PreviewRequest):
    query: str = Field(min_length=1, max_length=200)
    frame_step: int = Field(5, ge=1, le=120)


class JobRef(BaseModel):
    job_id: str
