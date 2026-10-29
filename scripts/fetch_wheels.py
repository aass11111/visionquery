"""Parallel, verified download of the backend's biggest PyPI wheels (Windows, Python 3.11).

Some connections cap the speed of each TCP connection (here ~11 KB/s each, ~170 KB/s with 8), and
pip downloads one file over one connection. This fetches the large wheels as many byte ranges at
once, checks each file against the sha256 PyPI publishes, and leaves them in a folder that
scripts/setup-windows.ps1 installs from before letting pip fetch the small remainder.

    python scripts/fetch_wheels.py            (standard library only)
Progress is written to fetch-wheels.json for scripts/setup-progress.ps1.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request

# Pinned to versions that satisfy torch 2.5.1, ultralytics 8.3 and backend/requirements.txt.
PACKAGES = [
    ("scipy", "1.15.3"), ("opencv-python", "4.12.0.88"), ("numpy", "2.1.1"), ("pandas", "2.2.3"),
    ("matplotlib", "3.10.0"), ("sympy", "1.13.1"), ("pillow", "11.0.0"), ("fonttools", "4.55.0"),
    ("pydantic-core", "2.27.1"), ("networkx", "3.4.2"), ("lap", "0.5.12"), ("mpmath", "1.3.0"),
    ("pytz", "2024.2"), ("tzdata", "2024.2"), ("pydantic", "2.10.3"), ("regex", "2024.11.6"),
    ("contourpy", "1.3.1"), ("seaborn", "0.13.2"), ("psutil", "6.1.0"), ("pyyaml", "6.0.2"),
    ("kiwisolver", "1.4.7"), ("polars-runtime-32", "2.1.0"), ("polars", "2.1.0"),
]
DEST = os.path.join(os.environ.get("TEMP", "."), "vq-wheels", "pypi")
PROGRESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fetch-wheels.json")
CONNECTIONS = 12          # simultaneous HTTP connections overall
RANGE_SIZE = 2 << 20      # big files are split into 2 MB ranges
UA = {"User-Agent": "visionquery-fetch/1.0"}

lock = threading.Lock()
state = {"got": 0, "total": 0, "files": 0, "done_files": 0, "current": "", "finished": False, "failed": []}


def get(url: str, headers: dict | None = None, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pick_wheel(name: str, version: str) -> dict | None:
    meta = json.loads(get(f"https://pypi.org/pypi/{name}/{version}/json"))
    files = [f for f in meta["urls"] if f["filename"].endswith(".whl")]

    def rank(fn: str) -> int:
        if "cp311-cp311-win_amd64" in fn:
            return 0
        if "abi3-win_amd64" in fn:
            return 1
        if fn.endswith("-none-any.whl"):
            return 2
        return 9

    files.sort(key=lambda f: rank(f["filename"]))
    return files[0] if files and rank(files[0]["filename"]) < 9 else None


def fetch_range(url: str, path: str, start: int, end: int) -> None:
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
                        state["got"] += len(block)
            if pos > end:
                return
        except Exception:
            time.sleep(min(2 + attempt, 10))
    raise RuntimeError(f"range {start}-{end} failed")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_progress() -> None:
    while True:
        with lock:
            snapshot = dict(state)
        tmp = PROGRESS + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(snapshot, f)
            os.replace(tmp, PROGRESS)
        except OSError:
            pass  # the progress bar has the file open right now; next second will do
        if snapshot["finished"]:
            return
        time.sleep(1)
        continue
        if snapshot["finished"]:
            return
        time.sleep(1)


def main() -> int:
    os.makedirs(DEST, exist_ok=True)
    threading.Thread(target=write_progress, daemon=True).start()

    with cf.ThreadPoolExecutor(8) as pool:
        picks = list(pool.map(lambda p: (p, pick_wheel(*p)), PACKAGES))

    todo = []
    for (name, version), w in picks:
        if w is None:
            print(f"skip {name} {version}: no Windows / Python 3.11 wheel")
            continue
        path = os.path.join(DEST, w["filename"])
        if os.path.exists(path) and os.path.getsize(path) == w["size"] and sha256(path) == w["digests"]["sha256"]:
            continue
        todo.append((w, path))
    state["files"] = len(todo)
    state["total"] = sum(w["size"] for w, _ in todo)
    print(f"{len(todo)} wheels, {state['total'] / 1048576:.0f} MB, {CONNECTIONS} connections", flush=True)

    for attempt in range(3):
        jobs = []
        with cf.ThreadPoolExecutor(CONNECTIONS) as pool:
            for w, path in todo:
                with open(path, "wb") as f:
                    f.truncate(w["size"])
                for start in range(0, w["size"], RANGE_SIZE):
                    end = min(start + RANGE_SIZE, w["size"]) - 1
                    jobs.append(pool.submit(fetch_range, w["url"], path, start, end))
            for j in cf.as_completed(jobs):
                j.result()
        bad = []
        for w, path in todo:
            if sha256(path) == w["digests"]["sha256"]:
                print(f"OK {w['filename']}", flush=True)
            else:
                bad.append((w, path))
        if not bad:
            break
        print(f"{len(bad)} file(s) failed sha256, downloading them again", flush=True)
        with lock:
            state["got"] -= sum(w["size"] for w, _ in bad)
        todo = bad
    with lock:
        state["failed"] = [w["filename"] for w, _ in todo] if bad else []
        state["finished"] = True
    time.sleep(1.5)
    if bad:
        print("FAILED: " + ", ".join(state["failed"]))
        return 1
    print("PYPI_WHEELS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
