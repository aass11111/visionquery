import csv
import os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIELDS: list[str] = [
    "query", "mode", "frame_step", "clip", "precision", "seconds",
    "frames_scanned", "hits", "peak_vram_gb", "tp", "fp",
    "precision_score", "recall", "f1",
]
KEY: tuple[str, ...] = ("query", "mode", "frame_step", "clip", "precision")


def _to_num(val):
    for fn in (int, float):
        try:
            return fn(val)
        except (ValueError, TypeError):
            pass
    return val


def load_rows(csv_path: str) -> list[dict]:
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [{k: _to_num(v) for k, v in row.items()} for row in csv.DictReader(f)]


def done_keys(rows: list[dict]) -> set[tuple]:
    return {tuple(str(row[k]) for k in KEY) for row in rows}


def append_row(csv_path: str, row: dict) -> None:
    exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "n/a") for k in FIELDS})


def write_markdown(rows: list[dict], path: str, best: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    by_query = defaultdict(list)
    for r in rows:
        by_query[r.get("query", "")].append(r)

    cols = [
        ("mode", "mode"), ("frame step", "frame_step"), ("CLIP", "clip"),
        ("precision", "precision"), ("time s", "seconds"), ("frames", "frames_scanned"),
        ("hits", "hits"), ("peak VRAM GB", "peak_vram_gb"), ("P", "precision_score"),
        ("R", "recall"), ("F1", "f1"),
    ]
    lines = ["# Benchmark results\n"]
    for q, q_rows in by_query.items():
        lines.append(f"### {q}\n")
        lines.append("| " + " | ".join(c[0] for c in cols) + " |")
        lines.append("| " + " | ".join("---" for _ in cols) + " |")
        for r in q_rows:
            lines.append("| " + " | ".join(str(r.get(c[1], "n/a")) for c in cols) + " |")
        lines.append("")

    lines.append("## Best settings")
    lines.append(f"- best_f1: {best.get('best_f1', 'n/a') if best else 'n/a'}")
    lines.append(f"- fastest_good: {best.get('fastest_good', 'n/a') if best else 'n/a'}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_charts(rows: list[dict], out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    modes = sorted({str(r["mode"]) for r in rows if "mode" in r})

    def _save(name: str, title: str, xlabel: str, ylabel: str, legend: bool = False):
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        if legend:
            plt.legend()
        plt.grid(True)
        plt.tight_layout()
        out_path = os.path.join(out_dir, name)
        plt.savefig(out_path, dpi=150)
        plt.close()
        saved.append(out_path)

    # time_vs_frame_step.png
    plt.figure()
    for m in modes:
        steps = defaultdict(list)
        for r in rows:
            if str(r.get("mode")) == m and isinstance(r.get("seconds"), (int, float)):
                try:
                    steps[int(r["frame_step"])].append(r["seconds"])
                except (ValueError, TypeError, KeyError):
                    pass
        if steps:
            xs = sorted(steps.keys())
            plt.plot(xs, [sum(steps[x]) / len(steps[x]) for x in xs], marker="o", label=m)
    _save("time_vs_frame_step.png", "Time vs Frame Step", "Frame Step", "Mean Seconds", legend=bool(modes))

    # f1_vs_frame_step.png (only if any numeric f1)
    if any(isinstance(r.get("f1"), (int, float)) for r in rows):
        plt.figure()
        for m in modes:
            steps = defaultdict(list)
            for r in rows:
                if str(r.get("mode")) == m and isinstance(r.get("f1"), (int, float)):
                    try:
                        steps[int(r["frame_step"])].append(r["f1"])
                    except (ValueError, TypeError, KeyError):
                        pass
            if steps:
                xs = sorted(steps.keys())
                plt.plot(xs, [sum(steps[x]) / len(steps[x]) for x in xs], marker="o", label=m)
        _save("f1_vs_frame_step.png", "F1 vs Frame Step", "Frame Step", "Mean F1", legend=bool(modes))

    # vram_peak.png
    plt.figure()
    vrams = defaultdict(list)
    for r in rows:
        p, v = r.get("precision"), r.get("peak_vram_gb")
        if p is not None and isinstance(v, (int, float)):
            vrams[str(p)].append(v)
    precs = sorted(vrams.keys())
    plt.bar(precs, [max(vrams[p]) for p in precs])
    _save("vram_peak.png", "Peak VRAM by Precision", "Precision", "Max Peak VRAM (GB)")

    # instant_vs_full.png
    plt.figure()
    queries = sorted({str(r["query"]) for r in rows if "query" in r})
    qm = defaultdict(lambda: defaultdict(list))
    for r in rows:
        q, m, s = r.get("query"), r.get("mode"), r.get("seconds")
        if q is not None and m is not None and isinstance(s, (int, float)):
            qm[str(q)][str(m)].append(s)
    if queries and modes:
        w = 0.8 / len(modes)
        for i, m in enumerate(modes):
            xs = [qi - 0.4 + w / 2 + i * w for qi in range(len(queries))]
            ys = [sum(qm[q][m]) / len(qm[q][m]) if qm[q][m] else 0.0 for q in queries]
            plt.bar(xs, ys, width=w, label=m)
        plt.xticks(range(len(queries)), queries)
    _save("instant_vs_full.png", "Instant vs Full Benchmark Time", "Query", "Mean Seconds", legend=bool(modes))

    return saved
