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

## Try it on Google Colab (free GPU)

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/aass11111/visionquery/blob/main/colab/VisionQuery.ipynb)

Pick **Runtime → Change runtime type → T4 GPU**, run the cells in order, and open the link the last setup cell prints.

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
