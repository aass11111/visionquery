import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    model_dir: Path = Path(os.getenv("MODEL_DIR", "./.models"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "./.data"))
    yolo_model: str = os.getenv("YOLO_MODEL", "yolov8s-worldv2.pt")
    sam_model: str = os.getenv("SAM_MODEL", "sam2.1_t.pt")
    clip_model: str = os.getenv("CLIP_MODEL", "ViT-B/32")
    device: str = os.getenv("DEVICE", "auto")  # auto | cuda | cpu
    yolo_imgsz: int = int(os.getenv("YOLO_IMGSZ", "640"))
    search_batch: int = int(os.getenv("SEARCH_BATCH", "8"))
    thumb_width: int = int(os.getenv("THUMB_WIDTH", "960"))
    max_hits: int = int(os.getenv("MAX_HITS", "2000"))
    # Frames a track may vanish before we give up re-attaching the target to a new track id.
    max_track_gap: int = int(os.getenv("MAX_TRACK_GAP", "20"))

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"


settings = Settings()
for d in (settings.model_dir, settings.videos_dir, settings.outputs_dir):
    d.mkdir(parents=True, exist_ok=True)
