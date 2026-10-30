"""Lazy model registry: only the models the current stage needs stay in GPU memory."""
import gc
import logging
import threading
from typing import Any

import numpy as np
import torch

from .config import settings

log = logging.getLogger("visionquery.models")


def pick_device() -> str:
    if settings.device in ("cuda", "cpu"):
        return settings.device if settings.device == "cpu" or torch.cuda.is_available() else "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


DEVICE = pick_device()

# GPU guard: this process may never take more than VRAM_FRACTION of the card, whatever runs.
if DEVICE == "cuda":
    torch.cuda.set_per_process_memory_fraction(min(max(settings.vram_fraction, 0.1), 1.0))


class ClipScorer:
    """Scores image crops against a text query with OpenAI CLIP, and embeds frames for the index."""

    def __init__(self) -> None:
        import clip

        self.model, self.preprocess = clip.load(settings.clip_model, device=DEVICE,
                                                download_root=str(settings.model_dir / "clip"))
        self.model.eval()
        self._tokenize = clip.tokenize
        self._text_cache: dict[str, torch.Tensor] = {}

    def _text(self, query: str) -> torch.Tensor:
        if query not in self._text_cache:
            with torch.no_grad():
                t = self.model.encode_text(self._tokenize([f"a photo of a {query}", query]).to(DEVICE))
                t = t / t.norm(dim=-1, keepdim=True)
                self._text_cache[query] = t.mean(0, keepdim=True)
        return self._text_cache[query]

    def score(self, crops_rgb: list[np.ndarray], query: str) -> list[float]:
        """Cosine similarity mapped to 0..1 (raw CLIP similarities live roughly in 0.15–0.35)."""
        if not crops_rgb:
            return []
        from PIL import Image

        batch = torch.stack([self.preprocess(Image.fromarray(c)) for c in crops_rgb]).to(DEVICE)
        with torch.no_grad():
            f = self.model.encode_image(batch)
            f = f / f.norm(dim=-1, keepdim=True)
            sims = (f @ self._text(query).T).squeeze(1).float().cpu().numpy()
        return [float(np.clip((s - 0.17) / 0.15, 0.0, 1.0)) for s in sims]

    def embed_images(self, images_rgb: list[np.ndarray]) -> np.ndarray:
        """L2-normalised image embeddings, float16 (N, 512)."""
        from PIL import Image

        if not images_rgb:
            return np.zeros((0, 512), np.float16)
        batch = torch.stack([self.preprocess(Image.fromarray(c)) for c in images_rgb]).to(DEVICE)
        with torch.no_grad():
            f = self.model.encode_image(batch)
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy().astype(np.float16)

    def embed_text(self, query: str) -> np.ndarray:
        return self._text(query).float().cpu().numpy()[0]


def to_unit(sim: np.ndarray) -> np.ndarray:
    """Raw CLIP cosine similarities (≈0.15–0.35 for text↔image) mapped to 0..1."""
    return np.clip((sim - 0.17) / 0.15, 0.0, 1.0)


def _load(name: str) -> Any:
    from ultralytics import SAM, YOLOWorld

    log.info("loading %s on %s", name, DEVICE)
    if name in ("yolo", "yolo_track", "yolo_live"):
        # Separate instances so ByteTrack callbacks from recolor never leak into search predictions.
        # Move to the GPU before set_classes(): the text embeddings it computes are created on the
        # model's current device, and stay there when predict() later moves the weights.
        m = YOLOWorld(str(settings.model_dir / settings.yolo_model))
        m.to(DEVICE)
        return m
    if name == "sam":
        m = SAM(str(settings.model_dir / settings.sam_model))
        m.to(DEVICE)
        return m
    if name == "clip":
        return ClipScorer()
    raise KeyError(name)


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()

    @property
    def loaded(self) -> list[str]:
        return sorted(self._models)

    def use(self, *names: str) -> dict[str, Any]:
        """Return the requested models, unloading every other one first to free VRAM."""
        wanted = {n for n in names if n}
        with self._lock:
            for n in list(self._models):
                if n not in wanted:
                    log.info("unloading %s", n)
                    del self._models[n]
            gc.collect()
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
            for n in wanted:
                if n not in self._models:
                    self._models[n] = _load(n)
            return {n: self._models[n] for n in wanted}


registry = ModelRegistry()


def vram() -> tuple[str | None, float | None, float | None, float | None]:
    """GPU name, total GB, used GB (whole card), and this app's cap in GB."""
    if DEVICE != "cuda":
        return None, None, None, None
    free, total = torch.cuda.mem_get_info()
    return (torch.cuda.get_device_name(0), round(total / 1e9, 1), round((total - free) / 1e9, 1),
            round(total * settings.vram_fraction / 1e9, 1))
