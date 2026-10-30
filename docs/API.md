# VisionQuery API

Base path `/api`. Types are defined in `frontend/src/types.ts`; the backend mirrors them in `backend/app/schemas.py`.
Long work runs as a **job** on a single GPU worker; progress streams over a WebSocket. Jobs are saved to disk and
resumed after the server restarts (power cuts).

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | | `Health` |
| POST | `/api/videos` | multipart `file` | `VideoMeta` (also queues the CLIP index job) |
| GET | `/api/videos/{video_id}` | | `VideoMeta` |
| GET | `/api/videos/{video_id}/stream` | | the video file (HTTP range supported) |
| GET | `/api/videos/{video_id}/frames/{index}.jpg` | | full frame JPEG (cached) |
| GET | `/api/videos/{video_id}/suggestions` | | `Suggestions` |
| GET | `/api/videos/{video_id}/index` | | `IndexStatus` |
| GET | `/api/translate?q=` | | `{ query_en, translated }` (Arabic → English, no GPU) |
| GET | `/api/command/parse?text=` | | `CommandParse` (no GPU) |
| POST | `/api/search` | `SearchRequest` | `{ job_id }` |
| POST | `/api/search-image` | multipart `video_id`, `file`, `top_k` | `{ job_id }` → `SearchResult` |
| POST | `/api/preview` | `PreviewRequest` | `image/jpeg` |
| POST | `/api/recolor` | `RecolorRequest` (1..8 targets) | `{ job_id }` → `RecolorResult` |
| POST | `/api/redact` | `RedactRequest` | `{ job_id }` → `RedactResult` |
| POST | `/api/command` | `CommandRequest` | `{ job_id }` → `CommandResult` |
| GET | `/api/jobs?active=1` | | `Job[]` (queued or running; used to re-attach after a refresh) |
| GET | `/api/jobs/{job_id}` | | `Job` |
| WS | `/api/jobs/{job_id}/ws` | | a `Job` JSON message on every change |
| WS | `/api/live?query=&conf=` | client sends JPEG frames (binary) | `LiveDetections` per frame |
| GET | `/api/outputs/{job_id}.mp4` | | rendered H.264 video |

## GPU guard
- One GPU job at a time; the process is capped at `VRAM_FRACTION` (default 0.6) of the card.
- Only the models a stage needs stay loaded; idle models are released.
- The CLIP index samples one frame every `INDEX_STEP_SEC` (0.5 s) in batches of 16, once per video.
- Instant search runs YOLO-World only on the ~top frames the index ranks for the query.
- Live mode is detection only, at most `LIVE_MAX_FPS` (3) frames/s; frames arriving while the GPU is busy are
  dropped. Blur/boxes are drawn in the browser.
- Masks are propagated between SAM 2 key frames with dense optical flow on the CPU.
