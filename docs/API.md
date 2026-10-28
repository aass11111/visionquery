# VisionQuery API

Base path `/api`. Types are defined in `frontend/src/types.ts`; the backend mirrors them in `backend/app/schemas.py`.
Long work (search, recolor) runs as a **job** on a single GPU worker; progress streams over a WebSocket.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | | `Health` |
| POST | `/api/videos` | multipart `file` | `VideoMeta` |
| GET | `/api/videos/{video_id}` | | `VideoMeta` |
| GET | `/api/videos/{video_id}/stream` | | the video file (HTTP range supported) |
| GET | `/api/videos/{video_id}/frames/{index}.jpg` | | full frame JPEG (cached) |
| GET | `/api/videos/{video_id}/suggestions` | | `Suggestions`: objects (and their colours) found in 12 sampled frames; cached |
| POST | `/api/search` | `SearchRequest` | `{ "job_id": str }` |
| POST | `/api/preview` | `PreviewRequest` | `image/jpeg`, one recoloured frame |
| POST | `/api/recolor` | `RecolorRequest` | `{ "job_id": str }` |
| GET | `/api/jobs/{job_id}` | | `Job` |
| WS | `/api/jobs/{job_id}/ws` | | a `Job` JSON message on every change; closes when done/error |
| GET | `/api/outputs/{job_id}.mp4` | | recoloured H.264 video |

## Pipeline
- **Search**: OpenCV reads one frame every `frame_step` frames → **YOLO-World** (classes = `[query]`) → optional
  **CLIP** re-rank of each crop against the query → frames with detections become `FrameHit`s.
- **Preview**: **SAM 2** segments the chosen box on one frame → LAB recolouring → JPEG.
- **Recolor**: YOLO-World + ByteTrack follow the chosen object through every frame (the track whose box best overlaps
  the chosen one); **SAM 2** re-segments it every `frame_step` frames and the mask is shifted/scaled with the tracked
  box in between; every frame is recoloured so the output never flickers; ffmpeg encodes H.264 and keeps the audio.

## Memory
Models load lazily and only the ones a stage needs stay on the GPU: search = YOLO-World + CLIP, preview = SAM 2,
recolor = YOLO-World + SAM 2. fp16 on CUDA.
