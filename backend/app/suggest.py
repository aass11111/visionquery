"""Search suggestions taken from the video itself: what objects appear, and in which colours."""
from collections import Counter, defaultdict

import cv2
import numpy as np

# COCO classes plus a few common extras; YOLO-World accepts any vocabulary.
VOCAB = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear",
    "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "sink", "refrigerator", "book", "clock", "vase", "scissors",
    "teddy bear", "van", "taxi", "helmet", "tree", "building", "flag",
]
# Objects where a colour makes a useful query ("red car"), as opposed to "red person".
COLOURABLE = {"car", "bus", "truck", "van", "taxi", "motorcycle", "bicycle", "boat", "backpack", "umbrella",
              "handbag", "suitcase", "chair", "couch", "bottle", "cup", "helmet", "kite", "sports ball"}
COLOURS = ["red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "white", "gray", "black"]


def color_name(crop_bgr: np.ndarray) -> str | None:
    """Dominant colour word of an object crop (centre region, to skip background at the edges)."""
    h, w = crop_bgr.shape[:2]
    if h < 6 or w < 6:
        return None
    c = crop_bgr[h // 5 : h - h // 5, w // 5 : w - w // 5]
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int32)
    hue, sat, val = hsv[:, 0], hsv[:, 1], hsv[:, 2]

    chromatic = (sat > 70) & (val > 50)
    if chromatic.mean() < 0.25:
        v = float(np.median(val))
        if v < 60:
            return "black"
        return "white" if v > 175 and float(np.median(sat)) < 40 else "gray"

    # OpenCV hue is 0..179; bins chosen so red wraps around both ends.
    hh = hue[chromatic]
    bins = {"red": ((hh < 8) | (hh >= 170)), "orange": (hh >= 8) & (hh < 20), "yellow": (hh >= 20) & (hh < 33),
            "green": (hh >= 33) & (hh < 85), "blue": (hh >= 85) & (hh < 130), "purple": (hh >= 130) & (hh < 150),
            "pink": (hh >= 150) & (hh < 170)}
    name = max(bins, key=lambda k: int(bins[k].sum()))
    if name == "orange" and float(np.median(val[chromatic])) < 140:
        return "brown"
    return name


def summarize(detections: list[tuple[int, str, str | None]], frames_sampled: int, limit: int = 14) -> list[dict]:
    """detections: (frame_index, label, colour). Returns objects by how often they appear, each followed by
    its two most common colours when a colour makes sense for that object."""
    frames: dict[str, set[int]] = defaultdict(set)
    counts: Counter[str] = Counter()
    colours: dict[str, Counter[str]] = defaultdict(Counter)
    for f, label, colour in detections:
        frames[label].add(f)
        counts[label] += 1
        if colour and label in COLOURABLE:
            colours[label][colour] += 1

    items: list[dict] = []
    for label in sorted(frames, key=lambda l: (-len(frames[l]), -counts[l])):
        items.append({"label": label, "count": counts[label], "frames": len(frames[label]), "kind": "object"})
        for colour, n in colours[label].most_common(2):
            if n >= 2 or counts[label] < 4:
                items.append({"label": f"{colour} {label}", "count": n, "frames": 0, "kind": "color"})
    return items[:limit]
