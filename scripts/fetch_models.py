"""Download the model weights over parallel connections before the first search.

ultralytics and CLIP fetch their weights over a single connection on first use, which on a
per-connection-capped line takes many minutes. This puts them where they are looked for:
  backend/.models/yolov8s-worldv2.pt, backend/.models/sam2.1_t.pt, backend/.models/clip/ViT-B-32.pt
  and ~/.cache/clip/ViT-B-32.pt (YOLO-World's own text encoder loads CLIP from there).
CLIP is checked against the sha256 in its URL; the ultralytics files by size.

    python scripts/fetch_models.py
"""
import concurrent.futures as cf
import hashlib
import os
import shutil
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "backend", ".models")
CLIP_URL = ("https://openaipublic.azureedge.net/clip/models/"
            "40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt")
FILES = [
    ("https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt",
     os.path.join(MODELS, "yolov8s-worldv2.pt"), None),
    ("https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2.1_t.pt",
     os.path.join(MODELS, "sam2.1_t.pt"), None),
    (CLIP_URL, os.path.join(MODELS, "clip", "ViT-B-32.pt"), CLIP_URL.split("/")[-2]),
]
CONNECTIONS = 12
RANGE_SIZE = 2 << 20
UA = {"User-Agent": "visionquery-fetch/1.0"}
lock = threading.Lock()
got = 0


def resolve(url: str) -> tuple[str, int]:
    """Follow redirects (GitHub release assets) and return the final URL and size."""
    req = urllib.request.Request(url, method="HEAD", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.geturl(), int(r.headers["Content-Length"])


def fetch_range(url: str, path: str, start: int, end: int) -> None:
    global got
    pos = start
    for attempt in range(20):
        try:
            req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={pos}-{end}"})
            with urllib.request.urlopen(req, timeout=60) as r, open(path, "r+b") as f:
                f.seek(pos)
                while pos <= end:
                    block = r.read(64 << 10)
                    if not block:
                        break
                    f.write(block)
                    pos += len(block)
                    with lock:
                        got += len(block)
            if pos > end:
                return
        except Exception:
            time.sleep(min(2 + attempt, 10))
    raise RuntimeError(f"range {start}-{end} of {url} failed")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    todo = []
    for url, path, sha in FILES:
        final, size = resolve(url)
        if os.path.exists(path) and os.path.getsize(path) == size and (sha is None or sha256(path) == sha):
            print(f"have {os.path.basename(path)}")
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.truncate(size)
        todo.append((final, path, size, sha))
    total = sum(t[2] for t in todo)
    print(f"{len(todo)} file(s), {total / 1048576:.0f} MB", flush=True)

    def report() -> None:
        while not done.is_set():
            print(f"progress {got / 1048576:.0f}/{total / 1048576:.0f} MB", flush=True)
            done.wait(15)

    done = threading.Event()
    threading.Thread(target=report, daemon=True).start()
    with cf.ThreadPoolExecutor(CONNECTIONS) as pool:
        jobs = [pool.submit(fetch_range, url, path, s, min(s + RANGE_SIZE, size) - 1)
                for url, path, size, _ in todo for s in range(0, size, RANGE_SIZE)]
        for j in cf.as_completed(jobs):
            j.result()
    done.set()

    for _, path, size, sha in todo:
        if os.path.getsize(path) != size or (sha and sha256(path) != sha):
            print(f"FAILED {path}")
            return 1
        print(f"OK {os.path.basename(path)}")

    cache = os.path.join(os.path.expanduser("~"), ".cache", "clip")
    os.makedirs(cache, exist_ok=True)
    if not os.path.exists(os.path.join(cache, "ViT-B-32.pt")):
        shutil.copy2(os.path.join(MODELS, "clip", "ViT-B-32.pt"), cache)
    print("MODELS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
