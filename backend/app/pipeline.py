"""Search, preview, recolor, redact and commands.

YOLO-World finds, CLIP confirms (and indexes frames for instant search), SAM 2 segments key frames, optical
flow carries masks in between, LAB recolouring / blur / pixelate paints. Long jobs checkpoint into
`job.workdir` so they continue after a restart.
"""
import json
import math
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch

from . import commands, index, video
from .arabic import translate
from .config import settings
from .jobs import Job
from .models import DEVICE, registry, to_unit
from .recolor import FlowPropagator, apply_effect, box_mask, clip_to_box, iou, smooth, warp_mask
from .schemas import (CommandRequest, CommandResult, Detection, FrameHit, ImageSearchRequest, PreviewRequest,
                      RecolorRequest, RecolorResult, RedactRequest, RedactResult, SearchRequest, SearchResult,
                      Suggestion, Suggestions, Target)
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


def _boxes(result) -> list[tuple[BoxT, float, int | None]]:
    b = result.boxes
    if b is None or len(b) == 0:
        return []
    xyxy = b.xyxy.cpu().numpy().tolist()
    conf = b.conf.cpu().numpy().tolist()
    ids = b.id.int().cpu().numpy().tolist() if b.id is not None else [None] * len(xyxy)
    return [(tuple(map(float, x)), float(c), i) for x, c, i in zip(xyxy, conf, ids)]


def _classes_of(result) -> list[int]:
    return [] if result.boxes is None else result.boxes.cls.int().cpu().numpy().tolist()


def _crop_rgb(frame: np.ndarray, box: BoxT, pad: float = 0.08) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    crop = frame[max(0, int(y1 - py)):min(h, int(y2 + py)), max(0, int(x1 - px)):min(w, int(x2 + px))]
    if crop.size == 0:
        crop = frame
    return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)


def _read_frames(video_id: str, wanted: list[int]):
    """Yield (index, frame) for sorted frame indices, grabbing (not decoding) the frames in between."""
    wanted = sorted(set(wanted))
    if not wanted:
        return
    cap = cv2.VideoCapture(str(video.source_path(video_id)))
    try:
        want = set(wanted)
        for idx in range(wanted[-1] + 1):
            if idx in want:
                ok, frame = cap.read()
                if not ok:
                    return
                yield idx, frame
            elif not cap.grab():
                return
    finally:
        cap.release()


# ---------------------------------------------------------------- search

def _detect_frames(job: Job, video_id: str, frames: list[int], yolo, clip, query_en: str, conf: float,
                   half: bool, fps: float, hits: list[FrameHit], progress: tuple[float, float]) -> int:
    """YOLO-World (+ CLIP re-rank) on the given frames; appends FrameHits. Returns frames processed."""
    scanned = 0
    batch: list[tuple[int, np.ndarray]] = []
    total = max(1, len(frames))

    def flush() -> None:
        nonlocal scanned
        if not batch:
            return
        results = yolo.predict([f for _, f in batch], conf=conf, imgsz=settings.yolo_imgsz, device=DEVICE,
                               half=half, verbose=False)
        for (idx, frame), res in zip(batch, results):
            dets = _boxes(res)
            if not dets:
                continue
            cs_all = clip.score([_crop_rgb(frame, b) for b, _, _ in dets], query_en) if clip else [None] * len(dets)
            detections = []
            for (box, det, _), cs in zip(dets, cs_all):
                if cs is not None and cs < 0.08:
                    continue  # CLIP is confident this crop is not what was asked for
                score = det if cs is None else 0.35 * det + 0.65 * cs
                detections.append(Detection(box=box, score=round(score, 4), det_score=round(det, 4),
                                            clip_score=None if cs is None else round(cs, 4), label=query_en))
            if detections and len(hits) < settings.max_hits:
                detections.sort(key=lambda d: d.score, reverse=True)
                hits.append(FrameHit(frame_index=idx, time=round(idx / fps, 3),
                                     thumbnail_url=video.save_thumbnail(video_id, idx, frame),
                                     detections=detections, best_score=detections[0].score))
        scanned += len(batch)
        batch.clear()
        lo, hi = progress
        job.update(progress=min(0.99, lo + (hi - lo) * scanned / total),
                   message=f"Checked {scanned:,}/{total:,} frames · {len(hits)} matches")

    for idx, frame in _read_frames(video_id, frames):
        batch.append((idx, frame))
        if len(batch) >= settings.search_batch:
            flush()
    flush()
    return scanned


def run_search(job: Job, req: SearchRequest) -> SearchResult:
    meta = video.get_meta(req.video_id)
    query = req.query.strip()
    query_en, translated = translate(query)
    query_en = query_en.lower()

    mode = req.mode
    if mode == "instant" and index.status(req.video_id).status != "ready":
        mode = "full"  # index not built yet: fall back instead of making the user wait

    job.update(message=f"Loading models · searching “{query_en}”")
    # CLIP is needed by instant mode (ranking) and by the re-rank option.
    models = registry.use("yolo", "clip" if (req.use_clip or mode == "instant") else "")
    yolo, clip = models["yolo"], models.get("clip")
    half = _set_classes(yolo, [query_en], req.yolo_half)
    rerank = clip if req.use_clip else None
    hits: list[FrameHit] = []

    if mode == "instant":
        ranked = index.rank(req.video_id, clip.embed_text(query_en), settings.instant_top_k)
        frames = [f for f, _ in ranked]
        scanned = _detect_frames(job, req.video_id, frames, yolo, rerank, query_en, req.conf, half, meta.fps,
                                 hits, (0.05, 0.99))
        hits.sort(key=lambda h: h.frame_index)
        return SearchResult(query=query, query_en=query_en, translated=translated, mode="instant",
                            frame_step=index.status(req.video_id).step, frames_scanned=scanned, hits=hits)

    # Full scan, checkpointed so a power cut does not restart it from frame 0.
    state_p = job.workdir / "search_state.json"
    start = 0
    if state_p.exists():
        st = json.loads(state_p.read_text())
        hits = [FrameHit.model_validate(h) for h in st["hits"]]
        start = st["next"]
    all_frames = list(range(0, meta.frame_count, req.frame_step))
    chunk = req.frame_step * settings.search_batch * 8
    scanned = sum(1 for f in all_frames if f < start)
    for lo in range(start, meta.frame_count, chunk):
        part = [f for f in all_frames if lo <= f < lo + chunk]
        p0, p1 = lo / meta.frame_count, min(1.0, (lo + chunk) / meta.frame_count)
        scanned += _detect_frames(job, req.video_id, part, yolo, rerank, query_en, req.conf, half, meta.fps,
                                  hits, (p0, p1))
        state_p.write_text(json.dumps({"next": lo + chunk, "hits": [h.model_dump() for h in hits]}))
    return SearchResult(query=query, query_en=query_en, translated=translated, mode="full",
                        frame_step=req.frame_step, frames_scanned=scanned, hits=hits)


def run_image_search(job: Job, req: ImageSearchRequest) -> SearchResult:
    """Query by example: CLIP ranks frames against the photo, YOLO-World proposes objects on those frames,
    and each object crop is compared with the photo."""
    meta = video.get_meta(req.video_id)
    if index.status(req.video_id).status != "ready":
        raise RuntimeError("The video index is still building — try again in a moment.")
    img = cv2.imread(req.image_path)
    if img is None:
        raise RuntimeError("Could not read the image")
    job.update(message="Loading CLIP + YOLO-World")
    models = registry.use("yolo", "clip")
    yolo, clip = models["yolo"], models["clip"]
    qvec = clip.embed_images([cv2.cvtColor(img, cv2.COLOR_BGR2RGB)])[0].astype(np.float32)
    ranked = index.rank(req.video_id, qvec, req.top_k)
    _set_classes(yolo, VOCAB)

    hits: list[FrameHit] = []
    frames = [f for f, _ in ranked]
    done = 0
    for idx, frame in _read_frames(req.video_id, frames):
        res = yolo.predict(frame, conf=0.2, imgsz=settings.yolo_imgsz, device=DEVICE, verbose=False)[0]
        dets = _boxes(res)
        classes = _classes_of(res)
        if dets:
            crops = clip.embed_images([_crop_rgb(frame, b) for b, _, _ in dets]).astype(np.float32)
            sims = crops @ qvec  # image↔image similarities are high (≈0.5–0.95)
            detections = []
            for (box, det, _), cls, s in zip(dets, classes, sims):
                score = float(np.clip((s - 0.55) / 0.35, 0, 1))
                if score > 0.15:
                    detections.append(Detection(box=box, score=round(score, 4), det_score=round(det, 4),
                                                clip_score=round(score, 4), label=VOCAB[cls]))
            if detections:
                detections.sort(key=lambda d: d.score, reverse=True)
                hits.append(FrameHit(frame_index=idx, time=round(idx / meta.fps, 3),
                                     thumbnail_url=video.save_thumbnail(req.video_id, idx, frame),
                                     detections=detections, best_score=detections[0].score))
        done += 1
        job.update(progress=done / max(1, len(frames)), message=f"Compared {done}/{len(frames)} frames")
    hits.sort(key=lambda h: h.frame_index)
    return SearchResult(query="image", query_en="image", translated=False, mode="instant",
                        frame_step=index.status(req.video_id).step, frames_scanned=done, hits=hits)


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
    for i, f in _read_frames(video_id, [int(i) for i in np.linspace(0, meta.frame_count - 1,
                                                                     min(samples, meta.frame_count))]):
        frames.append(f)
        idxs.append(i)

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


# ---------------------------------------------------------------- segmentation / preview

def segment(sam, frame: np.ndarray, box: BoxT) -> np.ndarray:
    """SAM 2 mask (float 0..1, frame size) for the object inside box."""
    h, w = frame.shape[:2]
    res = sam.predict(frame, bboxes=[list(box)], device=DEVICE, verbose=False)
    masks = res[0].masks if res else None
    if masks is None or len(masks.data) == 0:
        return box_mask((h, w), box, pad=0.0)
    m = masks.data[0].float().cpu().numpy()
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    return clip_to_box(m, box)


def preview(req: PreviewRequest) -> bytes:
    frame = video.read_frame(req.video_id, req.frame_index)
    sam = registry.use("sam")["sam"]
    mask = segment(sam, frame, req.box)
    out = apply_effect(frame, mask, req.effect, req.color, req.strength)
    return video.encode_jpeg(out, quality=90)


# ---------------------------------------------------------------- tracking

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


def _track_all(job: Job, video_id: str, queries: list[str], half: bool, progress_to: float, conf: float = 0.1
               ) -> tuple[dict[int, list[tuple[BoxT, int | None]]], int]:
    """Pass 1: YOLO-World + ByteTrack on every frame for all queries at once. Cached in the job folder."""
    cache = job.workdir / "tracks.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        return {int(k): [(tuple(b), t) for b, t in v] for k, v in d["tracks"].items()}, d["frames"]
    meta = video.get_meta(video_id)
    yolo = registry.use("yolo_track", "sam")["yolo_track"]
    _set_classes(yolo, queries, half)
    yolo.predictor = None  # fresh ByteTrack state for this video
    tracks: dict[int, list[tuple[BoxT, int | None]]] = defaultdict(list)
    cap = cv2.VideoCapture(str(video.source_path(video_id)))
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            res = yolo.track(frame, persist=idx > 0, tracker="bytetrack.yaml", conf=conf,
                             imgsz=settings.yolo_imgsz, device=DEVICE, half=half, verbose=False)
            tracks[idx] = [(b, t) for b, _, t in _boxes(res[0])]
            idx += 1
            if idx % 10 == 0:
                job.update(progress=progress_to * idx / meta.frame_count,
                           message=f"Tracking {idx:,}/{meta.frame_count:,}")
    finally:
        cap.release()
    cache.write_text(json.dumps({"frames": idx, "tracks": {k: v for k, v in tracks.items()}}))
    return tracks, idx


# ---------------------------------------------------------------- resumable segmented render

def _render(job: Job, video_id: str, frame_count: int, paint, progress: tuple[float, float], label: str) -> Path:
    """Render frames through `paint(i, frame, state) -> frame` into segments of SEGMENT_FRAMES frames.
    Finished segments survive a restart; the final video is the concatenation plus the source audio."""
    meta = video.get_meta(video_id)
    src = video.source_path(video_id)
    seg_dir = job.workdir / "segments"
    seg_dir.mkdir(exist_ok=True)
    n = settings.segment_frames
    lo, hi = progress
    for s in range(0, frame_count, n):
        seg = seg_dir / f"{s:08d}.mp4"
        if (seg_dir / f"{s:08d}.done").exists():
            continue
        writer = video.H264Writer(seg, meta.width, meta.height, meta.fps, audio_from=None)
        cap = cv2.VideoCapture(str(src))
        cap.set(cv2.CAP_PROP_POS_FRAMES, s)
        state: dict = {}  # fresh state per segment: masks are re-segmented at the segment start
        try:
            for i in range(s, min(s + n, frame_count)):
                ok, frame = cap.read()
                if not ok:
                    break
                writer.write(paint(i, frame, state))
                if i % 10 == 0:
                    job.update(progress=lo + (hi - lo) * i / frame_count,
                               message=f"{label} {i:,}/{frame_count:,}")
        finally:
            cap.release()
            writer.close()
        (seg_dir / f"{s:08d}.done").touch()

    out_path = settings.outputs_dir / f"{job.job_id}.mp4"
    listing = seg_dir / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in sorted(seg_dir.glob("*.mp4"))))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-i", str(src), "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac",
                        "-shortest", "-movflags", "+faststart", str(out_path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {r.stderr.strip()[-300:]}")
    shutil.rmtree(seg_dir, ignore_errors=True)
    return out_path


# ---------------------------------------------------------------- recolor (multi-target)

def _render_targets(job: Job, video_id: str, targets: list[Target], frame_step: int, half: bool,
                    progress: tuple[float, float]) -> RecolorResult:
    lo, hi = progress
    queries = []
    for t in targets:
        q = translate(t.query)[0].lower()
        if q not in queries:
            queries.append(q)
    job.update(message="Loading YOLO-World + SAM 2")
    tracks, frame_count = _track_all(job, video_id, queries, half, progress_to=lo + (hi - lo) * 0.4)
    paths = [_follow_target(tracks, t.frame_index, t.box, frame_count, search_window=max(2, frame_step))
             for t in targets]
    sam = registry.use("yolo_track", "sam")["sam"]
    flow = FlowPropagator()
    segmented = 0

    def paint(i: int, frame: np.ndarray, state: dict) -> np.ndarray:
        nonlocal segmented
        if state.get("last") != i - 1:
            flow.reset()
        state["last"] = i
        active = [(k, p[i]) for k, p in enumerate(paths) if i in p]
        if not active:
            flow.reset()
            return frame
        flow.step(frame)
        out = frame
        for k, box in active:
            t = targets[k]
            key_frame = state.get(f"key{k}", -10**9)
            if f"mask{k}" not in state or i - key_frame >= frame_step:
                m = segment(sam, frame, box)
                state[f"key{k}"] = i
                segmented += 1
            else:
                m = flow.propagate(state[f"mask{k}"])
                if m.max() < 0.3:  # flow lost it (cut, occlusion): fall back to moving with the box
                    m = warp_mask(state[f"mask{k}"], state[f"box{k}"], box)
                m = clip_to_box(m, box, pad=0.08)
            m = smooth(state.get(f"mask{k}"), m) if i - state.get(f"key{k}", i) > 0 else m
            state[f"mask{k}"], state[f"box{k}"] = m, box
            out = apply_effect(out, m, t.effect, t.color, t.strength)
        return out

    _render(job, video_id, frame_count, paint, (lo + (hi - lo) * 0.4, hi), "Rendering")
    return RecolorResult(output_url=f"/api/outputs/{job.job_id}.mp4", frames_written=frame_count,
                         frames_segmented=segmented, targets=len(targets))


def run_recolor(job: Job, req: RecolorRequest) -> RecolorResult:
    return _render_targets(job, req.video_id, req.targets, req.frame_step, req.yolo_half, (0.0, 1.0))


# ---------------------------------------------------------------- redact (hide every instance)

def run_redact(job: Job, req: RedactRequest) -> RedactResult:
    """Blur/pixelate every detection of a class in the whole video. Detector only (no SAM): boxes from key
    frames every `frame_step` frames are held and slightly grown in between — light on the GPU."""
    meta = video.get_meta(req.video_id)
    query_en = translate(req.query)[0].lower()
    cache = job.workdir / "boxes.json"
    if cache.exists():
        keyboxes = {int(k): v for k, v in json.loads(cache.read_text()).items()}
    else:
        job.update(message=f"Finding every “{query_en}”")
        yolo = registry.use("yolo")["yolo"]
        half = _set_classes(yolo, [query_en], req.yolo_half)
        keyframes = list(range(0, meta.frame_count, req.frame_step))
        keyboxes: dict[int, list] = {}
        batch: list[tuple[int, np.ndarray]] = []

        def flush() -> None:
            if not batch:
                return
            res = yolo.predict([f for _, f in batch], conf=req.conf, imgsz=settings.yolo_imgsz, device=DEVICE,
                               half=half, verbose=False)
            for (idx, _), r in zip(batch, res):
                keyboxes[idx] = [list(b) for b, _, _ in _boxes(r)]
            batch.clear()
            job.update(progress=0.5 * len(keyboxes) / max(1, len(keyframes)),
                       message=f"Detected on {len(keyboxes):,}/{len(keyframes):,} key frames")

        for idx, frame in _read_frames(req.video_id, keyframes):
            batch.append((idx, frame))
            if len(batch) >= settings.search_batch:
                flush()
        flush()
        cache.write_text(json.dumps(keyboxes))

    keys = sorted(keyboxes)
    hidden = 0

    def boxes_at(i: int) -> list:
        # Union of the boxes of the key frames around i: nothing slips through between detections.
        pos = np.searchsorted(keys, i)
        around = {keys[j] for j in (pos - 1, pos) if 0 <= j < len(keys)}
        return [b for k in around for b in keyboxes[k]]

    def paint(i: int, frame: np.ndarray, state: dict) -> np.ndarray:
        nonlocal hidden
        boxes = boxes_at(i)
        if not boxes:
            return frame
        h, w = frame.shape[:2]
        m = np.zeros((h, w), np.float32)
        for b in boxes:
            m = np.maximum(m, box_mask((h, w), b, pad=0.15))
        if i in keyboxes:
            hidden += len(keyboxes[i])
        return apply_effect(frame, m, req.effect, "#000000", 1.0)

    _render(job, req.video_id, meta.frame_count, paint, (0.5, 1.0), "Hiding")
    return RedactResult(output_url=f"/api/outputs/{job.job_id}.mp4", frames_written=meta.frame_count,
                        objects_hidden=hidden)


# ---------------------------------------------------------------- one-sentence commands

def run_command(job: Job, req: CommandRequest) -> CommandResult:
    parsed = commands.parse(req.text)
    if not parsed.ok:
        raise RuntimeError(parsed.error or "Could not understand the command")
    mode = "instant" if index.status(req.video_id).status == "ready" else "full"
    search_req = SearchRequest(video_id=req.video_id, query=parsed.object_en, frame_step=req.frame_step,
                               conf=req.conf, use_clip=True, yolo_half=req.yolo_half, mode=mode)
    job.update(message=f"Searching “{parsed.object_en}”")
    result = run_search(job, search_req)
    if not result.hits:
        return CommandResult(parse=parsed, search=result, recolor=None)
    best = max(result.hits, key=lambda h: h.best_score)
    det = best.detections[0]
    target = Target(query=parsed.object_en, frame_index=best.frame_index, box=det.box, effect=parsed.effect,
                    color=parsed.color or "#3b82f6", strength=0.9)
    rec = _render_targets(job, req.video_id, [target], req.frame_step, req.yolo_half, (0.3, 1.0))
    return CommandResult(parse=parsed, search=result, recolor=rec)
