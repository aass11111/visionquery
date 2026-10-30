import json


def load_labels(path: str | None) -> dict[str, list[tuple[int, int]]] | None:
    if path is None:
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    queries = data.get("queries", {})
    return {q: [tuple(r) for r in rngs] for q, rngs in queries.items()}


def score(hit_frames: list[int], ranges: list[tuple[int, int]], tolerance: int) -> dict:
    tp = sum(1 for f in hit_frames if any(s - tolerance <= f <= e + tolerance for s, e in ranges))
    fp = len(hit_frames) - tp
    precision = tp / len(hit_frames) if hit_frames else 0.0
    touched = sum(1 for s, e in ranges if any(s - tolerance <= f <= e + tolerance for f in hit_frames))
    recall = touched / len(ranges) if ranges else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def best_settings(rows: list[dict]) -> dict:
    valid = [r for r in rows if isinstance(r.get("f1"), (int, float))]
    if not valid:
        return {"best_f1": None, "fastest_good": None}
    best = max(valid, key=lambda r: r["f1"])
    good = [r for r in valid if r["f1"] >= 0.8 * best["f1"]]
    fastest = min(good, key=lambda r: r["seconds"]) if good else None
    return {"best_f1": best, "fastest_good": fastest}


if __name__ == "__main__":
    res = score([100, 250, 500], [(105, 200), (900, 950)], tolerance=10)
    assert res["tp"] == 1
    assert res["fp"] == 2
    assert res["precision"] == round(1 / 3, 4)
    assert res["recall"] == 0.5
    assert res["f1"] == 0.4

    empty = score([], [], tolerance=5)
    assert empty == {"tp": 0, "fp": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
