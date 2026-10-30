"""HTTP client for the VisionQuery API benchmark."""

import json
import os
import time
import urllib.error
import urllib.request
import uuid


class Api:
    """HTTP client for the VisionQuery API."""

    def __init__(self, base: str = "http://127.0.0.1:8000", max_wait_s: float = 120.0):
        """Initialize client with base URL and maximum retry wait time."""
        self.base = base.rstrip("/")
        self.max_wait_s = max_wait_s

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict | None = None,
    ) -> bytes:
        """Execute HTTP request with exponential backoff retry on connection errors."""
        deadline = time.monotonic() + self.max_wait_s
        delay = 1.0
        while True:
            try:
                req = urllib.request.Request(
                    f"{self.base}{path}", data=body, headers=headers or {}, method=method
                )
                with urllib.request.urlopen(req) as resp:
                    return resp.read()
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                now = time.monotonic()
                if now >= deadline:
                    raise
                time.sleep(min(delay, deadline - now))
                delay = min(delay * 2.0, 15.0)

    def _get_json(self, path: str) -> dict:
        """Perform a GET request and parse JSON response."""
        data = self._request("GET", path)
        return json.loads(data.decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        """Perform a POST request with JSON body and parse response."""
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        data = self._request("POST", path, body=body, headers=headers)
        return json.loads(data.decode("utf-8"))

    def health(self) -> dict:
        """GET /api/health."""
        return self._get_json("/api/health")

    def upload(self, path: str) -> dict:
        """POST /api/videos multipart field 'file' -> VideoMeta dict."""
        filename = os.path.basename(path)
        boundary = uuid.uuid4().hex
        with open(path, "rb") as f:
            content = f.read()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: video/mp4\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        data = self._request("POST", "/api/videos", body=body, headers=headers)
        return json.loads(data.decode("utf-8"))

    def wait_index(self, video_id: str, timeout_s: float = 900.0) -> dict:
        """Poll GET /api/videos/{id}/index every 1 s until status == 'ready'."""
        deadline = time.monotonic() + timeout_s
        while True:
            meta = self._get_json(f"/api/videos/{video_id}/index")
            if meta.get("status") == "ready":
                return meta
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Indexing timed out for video {video_id}")
            time.sleep(1.0)

    def search(self, req: dict, poll_s: float = 0.5) -> tuple[dict, float, float]:
        """POST /api/search, poll /api/jobs/{id} and health for peak VRAM."""
        start = time.monotonic()
        job = self._post_json("/api/search", req)
        job_id = job["job_id"]
        peak_vram = 0.0
        while True:
            health = self.health()
            peak_vram = max(peak_vram, float(health.get("vram_used_gb", 0.0)))
            status_info = self._get_json(f"/api/jobs/{job_id}")
            status = status_info.get("status")
            if status == "done":
                wall_s = time.monotonic() - start
                return status_info["result"], wall_s, peak_vram
            if status == "error":
                raise RuntimeError(status_info["error"])
            time.sleep(poll_s)
