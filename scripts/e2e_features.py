"""End-to-end check of every feature against a running backend (standard library only).

    python scripts/e2e_features.py [--api http://127.0.0.1:8000] [--video clip.mp4]

Without --video it builds a 4 s clip from ultralytics' bundled bus.jpg (needs ffmpeg and ultralytics in the
Python that runs it). Prints one line per feature with timing and the peak VRAM seen on /api/health.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

peak_vram = 0.0


def call(api: str, path: str, body: dict | None = None, raw: bytes | None = None, ctype: str | None = None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(api + path, data=data, method="POST" if data is not None else "GET")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=600) as r:
        out = r.read()
        return json.loads(out) if r.headers.get("Content-Type", "").startswith("application/json") else out


def multipart(fields: dict[str, str], file_field: str, path: str, mime: str) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{os.path.basename(path)}"'
                 f'\r\nContent-Type: {mime}\r\n\r\n'.encode() + open(path, "rb").read() + b"\r\n")
    return b"".join(parts) + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def watch_vram(api: str, stop: threading.Event) -> None:
    global peak_vram
    while not stop.is_set():
        try:
            peak_vram = max(peak_vram, call(api, "/api/health").get("vram_used_gb") or 0)
        except Exception:
            pass
        stop.wait(0.5)


def wait_job(api: str, job_id: str) -> dict:
    while True:
        j = call(api, f"/api/jobs/{job_id}")
        if j["status"] in ("done", "error"):
            if j["status"] == "error":
                raise RuntimeError(j["error"])
            return j["result"]
        time.sleep(0.5)


def make_clip() -> str:
    import ultralytics
    bus = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")
    out = os.path.join(tempfile.gettempdir(), "vq_clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", bus, "-vf",
                    "scale=1600:-2,crop=1280:720:'(iw-1280)*t/4':'(ih-720)*0.55'", "-t", "4", "-r", "25",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", out], check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--video")
    a = ap.parse_args()
    api = a.api
    stop = threading.Event()
    threading.Thread(target=watch_vram, args=(api, stop), daemon=True).start()
    health = call(api, "/api/health")
    print(f"health: {health['device']} {health['gpu_name']} cap={health['vram_cap_gb']} GB")

    path = a.video or make_clip()
    body, ctype = multipart({}, "file", path, "video/mp4")
    meta = call(api, "/api/videos", raw=body, ctype=ctype)
    vid = meta["video_id"]
    print(f"upload: {vid} {meta['frame_count']} frames")

    t = time.time()
    while call(api, f"/api/videos/{vid}/index")["status"] != "ready":
        time.sleep(0.5)
    idx = call(api, f"/api/videos/{vid}/index")
    print(f"index: {idx['frames_indexed']} frames in {time.time() - t:.1f}s")

    def search(q: str, mode: str) -> dict:
        t = time.time()
        r = wait_job(api, call(api, "/api/search", {"video_id": vid, "query": q, "frame_step": 5, "conf": 0.15,
                                                    "use_clip": True, "yolo_half": False, "mode": mode})["job_id"])
        print(f"search[{mode}] '{q}' -> '{r['query_en']}': {len(r['hits'])} hits / {r['frames_scanned']} frames "
              f"in {time.time() - t:.1f}s")
        return r

    full = search("bus", "full")
    search("bus", "instant")
    search("باص", "instant")
    search("شخص", "instant")

    for text in ["خلي الباص اخضر", "make the bus red"]:
        print(f"parse '{text}': {call(api, '/api/command/parse?text=' + urllib.request.quote(text))}")

    hit = max(full["hits"], key=lambda h: h["best_score"])
    det = hit["detections"][0]
    persons = search("person", "full")["hits"]
    targets = [{"query": "bus", "frame_index": hit["frame_index"], "box": det["box"], "effect": "recolor",
                "color": "#22c55e", "strength": 0.9}]
    if persons:
        p = max(persons, key=lambda h: h["best_score"])
        targets.append({"query": "person", "frame_index": p["frame_index"], "box": p["detections"][0]["box"],
                        "effect": "blur", "color": "#000000", "strength": 1.0})
    t = time.time()
    r = wait_job(api, call(api, "/api/recolor", {"video_id": vid, "targets": targets, "frame_step": 5,
                                                 "yolo_half": False})["job_id"])
    print(f"recolor x{r['targets']}: {r['frames_written']} frames, {r['frames_segmented']} SAM passes "
          f"in {time.time() - t:.1f}s -> {r['output_url']}")

    t = time.time()
    r = wait_job(api, call(api, "/api/redact", {"video_id": vid, "query": "شخص", "effect": "pixelate",
                                                "frame_step": 3, "conf": 0.2, "yolo_half": False})["job_id"])
    print(f"redact 'شخص': {r['objects_hidden']} hidden in {time.time() - t:.1f}s -> {r['output_url']}")

    t = time.time()
    r = wait_job(api, call(api, "/api/command", {"video_id": vid, "text": "خلي الباص احمر", "frame_step": 5,
                                                 "conf": 0.15, "yolo_half": False})["job_id"])
    rec = r["recolor"]
    print(f"command 'خلي الباص احمر' -> {r['parse']['effect']} {r['parse']['object_en']} {r['parse']['color_name']}: "
          f"{'rendered ' + rec['output_url'] if rec else 'no match'} in {time.time() - t:.1f}s")

    frame_jpg = os.path.join(tempfile.gettempdir(), "vq_query.jpg")
    with open(frame_jpg, "wb") as f:
        f.write(call(api, f"/api/videos/{vid}/frames/{hit['frame_index']}.jpg"))
    body, ctype = multipart({"video_id": vid, "top_k": "20"}, "file", frame_jpg, "image/jpeg")
    t = time.time()
    r = wait_job(api, call(api, "/api/search-image", raw=body, ctype=ctype)["job_id"])
    print(f"image search: {len(r['hits'])} hits in {time.time() - t:.1f}s")

    stop.set()
    print(f"peak VRAM (whole card): {peak_vram:.1f} GB  (app cap {health['vram_cap_gb']} GB)")
    print("FEATURES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
