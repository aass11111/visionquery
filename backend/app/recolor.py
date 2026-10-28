"""Mask maths and LAB recolouring. Pure NumPy/OpenCV so it is testable without a GPU."""
import cv2
import numpy as np


def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return b, g, r


def feather(mask: np.ndarray) -> np.ndarray:
    """Soft 0..1 alpha from a hard or soft mask; blur radius scales with object size."""
    m = mask.astype(np.float32)
    if m.max() > 1.0:
        m /= 255.0
    area = float((m > 0.5).sum())
    if area == 0:
        return m
    k = int(max(3, round(np.sqrt(area) * 0.02))) | 1
    return cv2.GaussianBlur(m, (k, k), 0)


def recolor_frame(frame: np.ndarray, mask: np.ndarray, hex_color: str, strength: float) -> np.ndarray:
    """Recolour the masked region of a BGR frame.

    Works in CIE LAB: chroma (a, b) is replaced by the target colour's, while lightness keeps the
    original texture and shading and is only shifted part of the way toward the target lightness.
    Specular highlights are kept so the surface still looks glossy.
    """
    alpha = feather(mask) * float(np.clip(strength, 0.0, 1.0))
    if alpha.max() <= 0:
        return frame

    target = cv2.cvtColor(np.uint8([[hex_to_bgr(hex_color)]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0]

    inside = alpha > 0.5
    mean_l = float(L[inside].mean()) if inside.any() else float(L.mean())
    new_l = np.clip(L + (target[0] - mean_l) * 0.55, 0, 255)

    # Slightly less chroma in deep shadow, like real paint.
    shade = 0.65 + 0.35 * (new_l / 255.0)
    new_a = 128 + (target[1] - 128) * shade
    new_b = 128 + (target[2] - 128) * shade

    highlight_keep = np.clip((248.0 - L) / 28.0, 0.0, 1.0)
    a = (alpha * highlight_keep)[..., None]
    new = np.stack([new_l, new_a, new_b], axis=-1)
    out = lab * (1 - a) + new * a
    return cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def warp_mask(mask: np.ndarray, src_box, dst_box) -> np.ndarray:
    """Move/scale a mask so that src_box lands on dst_box (cheap propagation between SAM calls)."""
    sx1, sy1, sx2, sy2 = map(float, src_box)
    dx1, dy1, dx2, dy2 = map(float, dst_box)
    kx = (dx2 - dx1) / max(sx2 - sx1, 1.0)
    ky = (dy2 - dy1) / max(sy2 - sy1, 1.0)
    m = np.float32([[kx, 0, dx1 - kx * sx1], [0, ky, dy1 - ky * sy1]])
    h, w = mask.shape[:2]
    warped = cv2.warpAffine(mask.astype(np.float32), m, (w, h), flags=cv2.INTER_LINEAR)
    return clip_to_box(warped, dst_box, pad=0.06)


def clip_to_box(mask: np.ndarray, box, pad: float = 0.06) -> np.ndarray:
    """Zero the mask outside a slightly padded box so colour never bleeds into the background."""
    h, w = mask.shape[:2]
    x1, y1, x2, y2 = map(float, box)
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    xa, ya = max(0, int(x1 - px)), max(0, int(y1 - py))
    xb, yb = min(w, int(np.ceil(x2 + px))), min(h, int(np.ceil(y2 + py)))
    out = np.zeros_like(mask, dtype=np.float32)
    out[ya:yb, xa:xb] = mask[ya:yb, xa:xb]
    return out


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0
