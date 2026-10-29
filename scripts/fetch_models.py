"""Download the model weights over parallel connections before the first search.

ultralytics and CLIP fetch their weights over a single connection on first use, which on a
per-connection-capped line takes many minutes. This puts them where they are looked for:
  backend/.models/yolov8s-worldv2.pt, backend/.models/sam2.1_t.pt, backend/.models/clip/ViT-B-32.pt
  and ~/.cache/clip/ViT-B-32.pt (YOLO-World's own text encoder loads CLIP from there).

Resumable across power cuts: files are pre-sized, and on a restart only the 2 MB ranges that
still end in zeros are fetched again. A finished file is then verified the way repair_wheel.py
does it (.pt files are ZIP archives: every member's CRC32 must pass, damaged members are
re-fetched), CLIP additionally against the sha256 in its URL. A `<file>.ok` marker records success.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repair_wheel import bad_ranges  # noqa: E402

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
TAIL = 64 << 10  # a range whose last 64 KB are all zeros was not finished
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


def unfinished_ranges(path: str, size: int) -> list[tuple[int, int]]:
    out = []
    with open(path, "rb") as f:
        for start in range(0, size, RANGE_SIZE):
            end = min(start + RANGE_SIZE, size) - 1
            tail = min(TAIL, end - start + 1)
            f.seek(end - tail + 1)
            if not any(f.read(tail)):
                out.append((start, end))
    return out


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    jobs, files = [], []
    for url, path, sha in FILES:
        if os.path.exists(path + ".ok"):
            print(f"have {os.path.basename(path)}")
            continue
        final, size = resolve(url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path) or os.path.getsize(path) != size:
            with open(path, "wb") as f:
                f.truncate(size)
        ranges = unfinished_ranges(path, size)
        files.append((final, path, size, sha))
        jobs += [(final, path, s, e) for s, e in ranges]
    total = sum(e - s + 1 for _, _, s, e in jobs)
    print(f"{len(files)} file(s) to finish, {total / 1048576:.0f} MB left", flush=True)

    done = threading.Event()

    def report() -> None:
        while not done.is_set():
            print(f"progress {got / 1048576:.0f}/{total / 1048576:.0f} MB", flush=True)
            done.wait(15)

    threading.Thread(target=report, daemon=True).start()
    with cf.ThreadPoolExecutor(CONNECTIONS) as pool:
        for j in cf.as_completed([pool.submit(fetch_range, *job) for job in jobs]):
            j.result()
    done.set()

    for url, path, size, sha in files:
        for round_ in range(5):
            bad = bad_ranges(path)  # ZIP members whose CRC32 fails
            if not bad:
                break
            print(f"{os.path.basename(path)}: {len(bad)} damaged member(s), re-fetching", flush=True)
            for s, e, _ in bad:
                fetch_range(url, path, s, e)
        if bad or (sha and sha256(path) != sha):
            print(f"FAILED {path}")
            return 1
        open(path + ".ok", "w").close()
        print(f"OK {os.path.basename(path)}", flush=True)

    cache = os.path.join(os.path.expanduser("~"), ".cache", "clip")
    os.makedirs(cache, exist_ok=True)
    if not os.path.exists(os.path.join(cache, "ViT-B-32.pt")):
        shutil.copy2(os.path.join(MODELS, "clip", "ViT-B-32.pt"), cache)
    print("MODELS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
