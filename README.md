# VisionQuery

**Natural-language video search and real-time object recoloring.**
Type what you are looking for ("red car", "person with a backpack"), see every moment it appears on a timeline,
pick one object and recolor it through the whole video while its shading and highlights stay realistic.

| Stage | Model / tool | Job |
|---|---|---|
| Find | **YOLO-World** (open-vocabulary YOLO) | boxes for any text query |
| Confirm | **CLIP** ViT-B/32 (optional) | re-scores crops for attribute-heavy queries (colour, clothing) |
| Segment & follow | **SAM 2** + ByteTrack | pixel mask of the chosen object, tracked across frames |
| Paint | OpenCV, CIE LAB | swaps chroma, keeps lightness texture and specular highlights |
| Serve | FastAPI + WebSocket, ffmpeg (H.264) | jobs with live progress, browser-playable output with audio |
| UI | React + TypeScript + Tailwind | player with box overlays, heat-map timeline, results grid, before/after |

The **frame-step slider** sets how often the models look at the video (every N frames): lower is more accurate,
higher is faster. Recoloring still renders every frame; between SAM 2 passes the mask is moved with the tracked box,
so the output never flickers. Only the models a stage needs are kept on the GPU.

## Features

| | |
|---|---|
| **Instant search** | A CLIP index (one frame / 0.5 s) is built after upload; searches rank it and run YOLO-World only on the best frames (0.5 s vs 3.5 s full scan on the test clip). |
| **Arabic queries** | `سيارة حمراء`, `چلب اسود`, `رجال لابس قميص ازرق` → English for the models; MSA + Iraqi dialect, dictionary-based, no GPU. |
| **One-sentence commands** | `خلي السيارة الحمراء زرقاء` / `make the red car blue` / `موّه الوجوه` search and edit the whole video. |
| **Search by image** | Drop a photo; the index finds similar moments and objects. |
| **Edit batch** | Up to 8 objects in one render, each recolor / blur / pixelate. |
| **Privacy** | Blur or pixelate every face, plate or person in the video (detector only). |
| **Live mode** | Webcam detection at ≤ 3 fps; effects drawn in the browser. |
| **Library** | Every upload is listed under the drop zone (open / delete). Stored in `Downloads\VisionQuery` — outside the project, never committed. Override with `DATA_DIR`. |
| **Power-cut safe** | Jobs are saved to disk and continue after a restart; renders are written in segments. |
| **GPU guard** | Process capped at 60 % of VRAM, one job at a time, live frames dropped when busy, optical flow on the CPU. Peak 2.6 GB on an RTX 3060 for every feature. |
| **Evaluation** | `scripts/benchmark.py` + `docs/EVALUATION.md` (bilingual chapter) + charts in `docs/eval/`. |

## Try it on Google Colab (free GPU)

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/aass11111/visionquery/blob/main/colab/VisionQuery.ipynb)

Pick **Runtime → Change runtime type → T4 GPU**, run the cells in order, and open the link the last setup cell prints.

## Run natively on Windows (NVIDIA GPU)

Tested on an RTX 3060: search ~9 s for 100 frames (first run includes model loading), preview ~1.3 s,
recolor of 100 frames ~17 s, 2.7 GB VRAM.

```bash
bash scripts/fetch-torch-wheels.sh                       # PyTorch CUDA, parallel + verified (slow lines)
python scripts/fetch_wheels.py                          # big PyPI wheels, parallel + verified
powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1   # Python 3.11, ffmpeg, venv
python scripts/fetch_models.py                          # YOLO-World, SAM 2, CLIP weights
cd frontend && npm install && npm run build && cd ..
```

Then start the server from `backend/` (it serves the built UI too) and open http://127.0.0.1:8000:

```powershell
$env:FRONTEND_DIST = '..\frontend\dist'; & "$HOME\.venvs\visionquery\Scripts\python.exe" -m uvicorn app.main:app --port 8000
```

`scripts/setup-progress.ps1` shows a live progress bar for every step. End-to-end check:
`PATH="$HOME/.venvs/visionquery/Scripts:$PATH" bash scripts/e2e.sh`.

## Run with Docker

```bash
# CPU (works anywhere, slow)
docker compose up --build

# NVIDIA GPU (needs the NVIDIA Container Toolkit)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

Open http://localhost:8080. Model weights download on first use into the `models` volume.

Approximate VRAM with the defaults (YOLO-World s, SAM 2.1 tiny, CLIP B/32, fp16): **~2 GB for search,
~3–4 GB for recoloring**. 6–8 GB GPUs are comfortable.

## Develop

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173  (proxies /api to :8000)
```

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

`http://localhost:5173/?demo` shows the UI with fake results, no backend needed.
Backend unit tests (recoloring and mask maths, no GPU): `cd backend && pytest`.

## Layout

```
backend/app/   main.py (API) · pipeline.py (search/preview/recolor) · models.py (lazy GPU registry)
               recolor.py (LAB painting, mask warp) · video.py (storage, frames, ffmpeg) · jobs.py (GPU queue)
frontend/src/  App.tsx · components/ · api/client.ts · types.ts (API contract)
docs/          API.md · DESIGN.md
```

---

## بالعربي

**VisionQuery** منصة تبحث داخل الفيديو بالكلام: تكتب وصف الشي اللي تريده، فيطلع لك وين ظهر على الـ Timeline. بعدها تختار جسم وتغيّر لونه بكل الفيديو، والظلال والإضاءة تبقى طبيعية.

- **YOLO-World** يلگى الجسم من النص، و **CLIP** يتأكد من الصفات، و **SAM 2** يقص الجسم ويتتبعه، و **LAB** يلوّنه.
- شريط الفريمات يحدد كل كم فريم يشتغل الموديل: أقل يعني أدق، وأكثر يعني أسرع.
- التشغيل: `docker compose up --build`، ومع كرت NVIDIA ضيف `-f docker-compose.gpu.yml`.
