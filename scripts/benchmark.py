"""Benchmark video search configurations across frame steps, modes, CLIP, and precision.

Usage:
    python scripts/benchmark.py --video path/to/video.mp4
    python scripts/benchmark.py --video path/to/video.mp4 --labels path/to/labels.json --out docs/eval
"""

import argparse
import itertools
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench.api import Api
from bench.metrics import load_labels, score, best_settings
from bench.report import FIELDS, load_rows, done_keys, append_row, write_markdown, write_charts


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark video search configurations")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--video", required=True)
    parser.add_argument("--labels", default=None)
    parser.add_argument("--queries", default="car,red car,person")
    parser.add_argument("--out", default="docs/eval")
    parser.add_argument("--frame-steps", default="1,5,10,30")
    parser.add_argument("--modes", default="instant,full")
    parser.add_argument("--clip", default="on,off")
    parser.add_argument("--precision", default="fp32,fp16")
    parser.add_argument("--cooldown", type=float, default=5.0)
    parser.add_argument("--max-runs", type=int, default=None)
    args = parser.parse_args()

    api = Api(args.api, 600)
    health = api.health()
    device = health.get("device", "") if isinstance(health, dict) else getattr(health, "device", "")

    labels = load_labels(args.labels)
    queries = list(labels.keys()) if labels else [q.strip() for q in args.queries.split(",") if q.strip()]
    frame_steps = [int(s.strip()) for s in args.frame_steps.split(",") if s.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    clips = [c.strip() for c in args.clip.split(",") if c.strip()]
    precisions = [p.strip() for p in args.precision.split(",") if p.strip()]
    if str(device).lower() == "cpu":
        precisions = [p for p in precisions if p != "fp16"]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"
    existing_rows = load_rows(csv_path) if csv_path.exists() else []
    done = done_keys(existing_rows)

    def is_done(q, fs, m, c, p):
        candidates = ((q, fs, m, c, p), (q, str(fs), m, c, p), f"{q}:{fs}:{m}:{c}:{p}")
        return any(k in done for k in candidates)

    combos = list(itertools.product(queries, frame_steps, modes, clips, precisions))
    runs = [item for item in combos if not is_done(*item)]
    if args.max_runs is not None:
        runs = runs[: args.max_runs]

    video_id = api.upload(args.video)
    if isinstance(video_id, dict):
        video_id = video_id.get("video_id", video_id.get("id", video_id))
    api.wait_index(video_id)

    for i, (q, fs, m, c, p) in enumerate(runs, 1):
        req = {
            "video_id": video_id,
            "query": q,
            "frame_step": fs,
            "conf": 0.15,
            "use_clip": c == "on",
            "yolo_half": p == "fp16",
            "mode": m,
        }
        result, seconds, peak_vram_gb = api.search(req)
        hits = result.get("hits", result) if isinstance(result, dict) else result
        hit_frames = [h["frame_index"] for h in hits]

        if labels:
            m_res = score(hit_frames, labels.get(q, []), tolerance=fs)
            tp, fp = m_res.get("tp", 0), m_res.get("fp", 0)
            prec_score, recall, f1 = m_res.get("precision", 0.0), m_res.get("recall", 0.0), m_res.get("f1", 0.0)
        else:
            tp = fp = prec_score = recall = f1 = "n/a"

        row = {
            "video_id": video_id,
            "query": q,
            "frame_step": fs,
            "mode": m,
            "clip": c,
            "precision": p,
            "seconds": round(seconds, 3),
            "frames_scanned": result.get("frames_scanned", "n/a") if isinstance(result, dict) else "n/a",
            "peak_vram_gb": peak_vram_gb,
            "hits": len(hit_frames),
            "tp": tp,
            "fp": fp,
            "precision_score": prec_score,
            "recall": recall,
            "f1": f1,
        }
        if FIELDS and all(k in row for k in FIELDS):
            row = {k: row[k] for k in FIELDS}
        append_row(csv_path, row)

        f1_disp = f"{f1:.2f}" if isinstance(f1, (int, float)) else f1
        print(f"[{i}/{len(runs)}] {q} {m} {fs} {c} {p}: {seconds:.1f}s hits={len(hit_frames)} F1={f1_disp}")
        if args.cooldown > 0:
            time.sleep(args.cooldown)

    all_rows = load_rows(csv_path) if csv_path.exists() else []
    best = best_settings(all_rows)
    md_path = out_dir / "results.md"
    write_markdown(all_rows, md_path, best)
    write_charts(all_rows, out_dir)
    print(f"Results CSV: {csv_path}")
    print(f"Markdown report: {md_path}")
    print(f"Charts directory: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
