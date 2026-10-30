"""Pydantic mirror of frontend/src/types.ts."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Box = tuple[float, float, float, float]
Effect = Literal["recolor", "blur", "pixelate"]
SearchMode = Literal["instant", "full"]


def _hex(v: str) -> str:
    v = v.strip()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) != 7 or any(c not in "0123456789abcdefABCDEF" for c in v[1:]):
        raise ValueError("color must be #RRGGBB")
    return v.lower()


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
    vram_cap_gb: Optional[float]
    loaded_models: list[str]
    busy: bool


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
    query_en: str
    translated: bool
    mode: SearchMode
    frame_step: int
    frames_scanned: int
    hits: list[FrameHit]


class Suggestion(BaseModel):
    label: str
    count: int  # detections across the sampled frames
    frames: int  # sampled frames containing it (0 for colour variants)
    kind: Literal["object", "color"]


class Suggestions(BaseModel):
    video_id: str
    frames_sampled: int
    items: list[Suggestion]


class IndexStatus(BaseModel):
    video_id: str
    status: Literal["none", "building", "ready"]
    frames_indexed: int
    step: int


class LibraryItem(BaseModel):
    meta: VideoMeta
    created: float
    thumbnail_url: str
    index_status: Literal["none", "building", "ready"]
    outputs: int
    bytes: int
    busy: bool


class Library(BaseModel):
    path: str
    total_bytes: int
    videos: list[LibraryItem]


class Target(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    frame_index: int = Field(ge=0)
    box: Box
    effect: Effect = "recolor"
    color: str = "#3b82f6"
    strength: float = Field(0.85, ge=0, le=1)

    @field_validator("color")
    @classmethod
    def check_color(cls, v: str) -> str:
        return _hex(v)


class RecolorResult(BaseModel):
    output_url: str
    frames_written: int
    frames_segmented: int
    targets: int


class RedactResult(BaseModel):
    output_url: str
    frames_written: int
    objects_hidden: int


class CommandParse(BaseModel):
    ok: bool
    object: Optional[str]
    object_en: Optional[str]
    color: Optional[str]
    color_name: Optional[str]
    effect: Effect
    error: Optional[str]


class CommandResult(BaseModel):
    parse: CommandParse
    search: SearchResult
    recolor: Optional[RecolorResult]


class SearchRequest(BaseModel):
    video_id: str
    query: str = Field(min_length=1, max_length=200)
    frame_step: int = Field(5, ge=1, le=120)
    conf: float = Field(0.15, ge=0.01, le=0.95)
    use_clip: bool = True
    yolo_half: bool = False  # run YOLO-World in FP16 (faster, CUDA only)
    mode: SearchMode = "instant"


class ImageSearchRequest(BaseModel):
    """Stored with the job so an image search can be resumed; the image lives in the job folder."""
    video_id: str
    image_path: str
    top_k: int = Field(40, ge=5, le=200)


class IndexRequest(BaseModel):
    video_id: str


class PreviewRequest(BaseModel):
    video_id: str
    frame_index: int = Field(ge=0)
    box: Box
    effect: Effect = "recolor"
    color: str = "#3b82f6"
    strength: float = Field(0.85, ge=0, le=1)

    @field_validator("color")
    @classmethod
    def check_color(cls, v: str) -> str:
        return _hex(v)


class RecolorRequest(BaseModel):
    video_id: str
    targets: list[Target] = Field(min_length=1, max_length=8)
    frame_step: int = Field(5, ge=1, le=120)
    yolo_half: bool = False


class RedactRequest(BaseModel):
    video_id: str
    query: str = Field(min_length=1, max_length=200)
    effect: Literal["blur", "pixelate"] = "blur"
    frame_step: int = Field(3, ge=1, le=60)
    conf: float = Field(0.2, ge=0.01, le=0.95)
    yolo_half: bool = False


class CommandRequest(BaseModel):
    video_id: str
    text: str = Field(min_length=2, max_length=300)
    frame_step: int = Field(5, ge=1, le=120)
    conf: float = Field(0.15, ge=0.01, le=0.95)
    yolo_half: bool = False


class JobRef(BaseModel):
    job_id: str
