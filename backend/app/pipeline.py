"""Search, preview and recolor: YOLO-World finds, CLIP confirms, SAM 2 segments, LAB recolouring paints."""
import math
from collections import defaultdict

import cv2
import numpy as np
import torch

from . import video
from .config import settings
from .jobs import Job
from .models import DEVICE, registry
from .recolor import clip_to_box, iou, recolor_frame, warp_mask
from .schemas import (Detection, FrameHit, PreviewRequest, RecolorRequest, RecolorResult, SearchRequest,
                      SearchResult, Suggestion, Suggestions)
from .suggest import VOCAB, color_name, summarize

BoxT = tuple[float, float, float, float]


def _set_classes(yolo, classes: list[str], half: bool = False) -> bool:
    """Point YOLO-World at a vocabulary in the requested precision; returns the effective `half`.

    The text embeddings set_classes() computes are float32 and are not converted when ultralytics
    turns the weights to fp16, so we cast them ourselves to match (FP16 mode) or keep the whole
    model in float32 (FP32 mode, the default and the safest)."""
    half = half and DEVICE == "cuda"
    if getattr(yolo, "_vq_half", None) != half:
        # Precision changed: drop the predictor so ultralytics re-wraps the weights in the new dtype.
        yolo.predictor = None
        yolo.model.float()
        yolo._vq_half = half
        yolo._vq_classes = None
    key = tuple(classes)
    if getattr(yolo, "_vq_classes", None) != key:
        yolo.model.to(DEVICE)
        yolo.set_classes(list(classes))
        yolo._vq_classes = key
    txt = getattr(yolo.model, "txt_feats", None)
    if txt is not None:
        yolo.model.txt_feats = txt.to(DEVICE, dtype=torch.float16 if half else torch.float32)
    return half


def _set_query(yolo, query: str, half: bool = False) -> bool:
    return _set_classes(yolo, [query], half)


def _boxes(result) -> list[tuple[BoxT, float, int | None]]:
    b = result.boxes
    if b is None or len(b) == 0:
        return []
    xyxy = b.xyxy.cpu().numpy().tolist()
    conf = b.conf.cpu().numpy().tolist()
    ids = b.id.int().cpu().numpy().tolist() if b.id is not None else [None] * len(xyxy)
    return [(tuple(map(float, x)), float(c), i) for x, c, i in zip(xyxy, conf, ids)]


def _crop_rgb(frame: np.ndarray, box: BoxT, pad: float = 0.08) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    crop = frame[max(0, int(y1 - py)):min(h, int(y2 + py)), max(0, int(x1 - px)):min(w, int(x2 + px))]
    if crop.size == 0:
        crop = frame
    return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------- search

def run_search(job: Job, req: SearchRequest) -> SearchResult:
    meta = video.get_meta(req.video_id)
    query = req.query.strip().lower()
    job.update(message="Loading YOLO-World" + (" + CLIP" if req.use_clip else ""))
    models = registry.use("yolo", "clip" if req.use_clip else "")
    yolo, clip = models["yolo"], models.get("clip")
    half = _set_query(yolo, query, req.yolo_half)

    step = req.frame_step
    total = math.ceil(meta.frame_count / step)
    hits: list[FrameHit] = []
    scanned = 0
    batch_idx: list[int] = []
    batch: list[np.ndarray] = []

    def flush() -> None:
        nonlocal scanned
        if not batch:
            return
        results = yolo.predict(batch, conf=req.conf, imgsz=settings.yolo_imgsz, device=DEVICE, half=half,
                               verbose=False)
        for idx, frame, res in zip(batch_idx, batch, results):
            dets = _boxes(res)
            if not dets:
                continue
            clip_scores = clip.score([_crop_rgb(frame, b) for b, _, _ in dets], query) if clip else [None] * len(dets)
            detections = []
            for (box, det, _), cs in zip(dets, clip_scores):
                score = det if cs is None else 0.35 * det + 0.65 * cs
                if cs is not None and cs < 0.08:
                    continue  # CLIP is confident this crop is not what was asked for
                detections.append(Detection(box=box, score=round(score, 4), det_score=round(det, 4),
                                            clip_score=None if cs is None else round(cs, 4), label=query))
            if not detections or len(hits) >= settings.max_hits:
                continue
            detections.sort(key=lambda d: d.score, reverse=True)
            hits.append(FrameHit(frame_index=idx, time=round(idx / meta.fps, 3),
                                 thumbnail_url=video.save_thumbnail(req.video_id, idx, frame),
                                 detections=detections, best_score=detections[0].score))
        scanned += len(batch)
        batch.clear()
        batch_idx.clear()
        job.update(progress=min(0.99, scanned / total),
                   message=f"Scanned {scanned:,}/{total:,} frames · {len(hits)} matches")

    cap = cv2.VideoCapture(str(video.source_path(req.video_id)))
    idx = 0
    try:
        while True:
            if idx % step == 0:
                ok, frame = cap.read()
                if not ok:
                    break
                batch.append(frame)
                batch_idx.append(idx)
                if len(batch) >= settings.search_batch:
                    flush()
            elif not cap.grab():
                break
            idx += 1
        flush()
    finally:
        cap.release()

    return SearchResult(query=query, frame_step=step, frames_scanned=scanned, hits=hits)


# ---------------------------------------------------------------- suggestions

def suggestions(video_id: str, samples: int = 12) -> Suggestions:
    """What is actually in the video: YOLO-World over a broad vocabulary on a few evenly spaced frames,
    plus the dominant colour of each object. Cached per video."""
    cache = video.video_dir(video_id) / "suggestions.json"
    if cache.exists():
        return Suggestions.model_validate_json(cache.read_text())

    meta = video.get_meta(video_id)
    yolo = registry.use("yolo")["yolo"]
    half = _set_classes(yolo, VOCAB)  # FP32: runs once per video, accuracy over speed

    frames, idxs = [], []
    for i in np.linspace(0, meta.frame_count - 1, min(samples, meta.frame_count)).astype(int):
        try:
            frames.append(video.read_frame(video_id, int(i)))
            idxs.append(int(i))
        except IndexError:
            continue

    dets: list[tuple[int, str, str | None]] = []
    if frames:
        results = yolo.predict(frames, conf=0.3, imgsz=settings.yolo_imgsz, device=DEVICE, half=half, verbose=False)
        for idx, frame, res in zip(idxs, frames, results):
            if res.boxes is None:
                continue
            for box, cls in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.cls.cpu().numpy()):
                x1, y1, x2, y2 = map(int, box)
                dets.append((idx, VOCAB[int(cls)], color_name(frame[max(0, y1):y2, max(0, x1):x2])))

    out = Suggestions(video_id=video_id, frames_sampled=len(frames),
                      items=[Suggestion(**s) for s in summarize(dets, len(frames))])
    cache.write_text(out.model_dump_json())
    return out


# ---------------------------------------------------------------- segmentation

def segment(sam, frame: np.ndarray, box: BoxT) -> np.ndarray:
    """SAM 2 mask (float 0..1, frame size) for the object inside box."""
    h, w = frame.shape[:2]
    res = sam.predict(frame, bboxes=[list(box)], device=DEVICE, verbose=False)
    masks = res[0].masks if res else None
    if masks is None or len(masks.data) == 0:
        m = np.zeros((h, w), np.float32)
        x1, y1, x2, y2 = map(int, box)
        cv2.ellipse(m, ((x1 + x2) // 2, (y1 + y2) // 2), ((x2 - x1) // 2, (y2 - y1) // 2), 0, 0, 360, 1.0, -1)
        return m
    m = masks.data[0].float().cpu().numpy()
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    return clip_to_box(m, box)


def preview(req: PreviewRequest) -> bytes:
    frame = video.read_frame(req.video_id, req.frame_index)
    sam = registry.use("sam")["sam"]
    mask = segment(sam, frame, req.box)
    return video.encode_jpeg(recolor_frame(frame, mask, req.color, req.strength), quality=90)


# ---------------------------------------------------------------- recolor

def _follow_target(tracks: dict[int, list[tuple[BoxT, int | None]]], start: int, box: BoxT,
                   frame_count: int, search_window: int) -> dict[int, BoxT]:
    """Pick the track that matches the user's box, then walk forward and backward, re-attaching to a new
    track id when ByteTrack loses and re-creates the object (occlusion, fast motion)."""
    anchor, best = None, 0.0
    for f in range(max(0, start - search_window), min(frame_count, start + search_window + 1)):
        for b, tid in tracks.get(f, []):
            s = iou(b, box) - abs(f - start) * 1e-3
            if s > best:
                anchor, best = (f, tid, b), s
    if anchor is None or best < 0.2:
        raise RuntimeError("Could not lock onto the selected object — try another frame or a lower frame step.")

    out: dict[int, BoxT] = {anchor[0]: anchor[2]}
    for direction in (1, -1):
        tid, last_box, last_f = anchor[1], anchor[2], anchor[0]
        f = anchor[0] + direction
        while 0 <= f < frame_count and abs(f - last_f) <= settings.max_track_gap:
            cands = tracks.get(f, [])
            same = [b for b, t in cands if t is not None and t == tid]
            if same:
                chosen = same[0]
            else:
                scored = [(iou(b, last_box), b, t) for b, t in cands]
                scored = [s for s in scored if s[0] > 0.3]
                chosen = None
                if scored:
                    _, chosen, new_tid = max(scored, key=lambda s: s[0])
                    tid = new_tid if new_tid is not None else tid
            if chosen is not None:
                out[f] = chosen
                last_box, last_f = chosen, f
            f += direction
    return out


def run_recolor(job: Job, req: RecolorRequest) -> RecolorResult:
    meta = video.get_meta(req.video_id)
    query = req.query.strip().lower()
    src = video.source_path(req.video_id)

    job.update(message="Loading YOLO-World + SAM 2")
    models = registry.use("yolo_track", "sam")
    yolo, sam = models["yolo_track"], models["sam"]
    half = _set_query(yolo, query, req.yolo_half)

    # Pass 1: track every frame (YOLO-World is cheap); keep only boxes.
    tracks: dict[int, list[tuple[BoxT, int | None]]] = defaultdict(list)
    cap = cv2.VideoCapture(str(src))
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            res = yolo.track(frame, persist=idx > 0, tracker="bytetrack.yaml", conf=0.1,
                             imgsz=settings.yolo_imgsz, device=DEVICE, half=half, verbose=False)
            tracks[idx] = [(b, t) for b, _, t in _boxes(res[0])]
            idx += 1
            if idx % 10 == 0:
                job.update(progress=0.45 * idx / meta.frame_count, message=f"Tracking {idx:,}/{meta.frame_count:,}")
    finally:
        cap.release()
    frame_count = idx
    target = _follow_target(tracks, req.frame_index, req.box, frame_count, search_window=max(2, req.frame_step))

    # Pass 2: SAM 2 every `frame_step` frames, warp the mask in between, recolour every frame.
    out_path = settings.outputs_dir / f"{job.job_id}.mp4"
    writer = video.H264Writer(out_path, meta.width, meta.height, meta.fps, audio_from=src)
    cap = cv2.VideoCapture(str(src))
    mask, mask_box, mask_frame = None, None, -10**9
    segmented = 0
    try:
        for i in range(frame_count):
            ok, frame = cap.read()
            if not ok:
                break
            box = target.get(i)
            if box is not None:
                if mask is None or i - mask_frame >= req.frame_step:
                    mask, mask_box, mask_frame = segment(sam, frame, box), box, i
                    segmented += 1
                    cur = mask
                else:
                    cur = warp_mask(mask, mask_box, box)
                frame = recolor_frame(frame, cur, req.color, req.strength)
            writer.write(frame)
            if i % 10 == 0:
                job.update(progress=0.45 + 0.55 * i / frame_count,
                           message=f"Rendering {i:,}/{frame_count:,} · {segmented} SAM passes")
    finally:
        cap.release()
        writer.close()

    return RecolorResult(output_url=f"/api/outputs/{job.job_id}.mp4", frames_written=frame_count,
                         frames_segmented=segmented)
