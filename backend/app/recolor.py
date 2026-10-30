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


CHROMATIC = 20.0        # LAB chroma above which a pixel counts as coloured
PAINTED_SHARE = 0.2     # an object with at least this share of coloured pixels is "painted"


def paint_weight(lab: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Per-pixel 0..1 weight of how much a pixel is part of the object's paint.

    Chroma = distance from grey in the a/b plane. Real objects mix paint with neutral parts (a bus
    is often more dark glass and white lettering than blue), so the decision uses the share of
    coloured pixels, not their median. On a painted object, pixels well below the paint's typical
    chroma (lettering, tyres, windows) fade out of the recolour with a smooth ramp; on a neutral
    object (a white car) every pixel is paint."""
    chroma = np.hypot(lab[..., 1] - 128.0, lab[..., 2] - 128.0)
    if not inside.any():
        return np.ones(chroma.shape, np.float32)
    obj = chroma[inside]
    coloured = obj > CHROMATIC
    if coloured.mean() < PAINTED_SHARE:
        return np.ones(chroma.shape, np.float32)
    typical = float(np.median(obj[coloured]))
    lo, hi = 8.0, max(12.0, typical * 0.5)
    t = np.clip((chroma - lo) / (hi - lo), 0.0, 1.0)
    return (t * t * (3 - 2 * t)).astype(np.float32)  # smoothstep


def recolor_frame(frame: np.ndarray, mask: np.ndarray, hex_color: str, strength: float) -> np.ndarray:
    """Recolour the masked region of a BGR frame.

    Works in CIE LAB: chroma (a, b) is replaced by the target colour's, while lightness keeps the
    original texture and shading and is only shifted part of the way toward the target lightness.
    Specular highlights are kept so the surface still looks glossy.

    On a coloured object (a blue bus), neutral parts such as white lettering, black tyres or chrome
    keep their colour, like a real repaint. A neutral object (a white or grey car) is recoloured
    as a whole, since its "paint" is the neutral colour itself.
    """
    alpha = feather(mask) * float(np.clip(strength, 0.0, 1.0))
    if alpha.max() <= 0:
        return frame

    target = cv2.cvtColor(np.uint8([[hex_to_bgr(hex_color)]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0]

    inside = alpha > 0.5
    alpha = alpha * paint_weight(lab, inside)
    painted = alpha > 0.5
    ref = painted if painted.any() else inside
    mean_l = float(L[ref].mean()) if ref.any() else float(L.mean())
    new_l = np.clip(L + (target[0] - mean_l) * 0.55, 0, 255)

    # Slightly less chroma in deep shadow, like real paint.
    shade = 0.65 + 0.35 * (new_l / 255.0)
    new_a = 128 + (target[1] - 128) * shade
    new_b = 128 + (target[2] - 128) * shade

    highlight_keep = np.clip((248.0 - L) / 28.0, 0.0, 1.0)
    a = (alpha * highlight_keep)[..., None]
    new = np.stack([new_l, new_a, new_b], axis=-1)
    painted = cv2.cvtColor(np.clip(new, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
    # Blend in BGR so pixels outside the mask are bit-identical (a LAB round trip would shift them by ±1).
    out = frame.astype(np.float32) * (1 - a) + painted * a
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def blur_region(frame: np.ndarray, mask: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Heavy Gaussian blur inside the (feathered) mask, for privacy redaction."""
    alpha = feather(mask) * float(np.clip(strength, 0.0, 1.0))
    if alpha.max() <= 0:
        return frame
    h, w = frame.shape[:2]
    k = int(max(15, round(min(h, w) * 0.06))) | 1
    small = cv2.resize(frame, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    blurred = cv2.resize(cv2.GaussianBlur(small, (k // 4 | 1, k // 4 | 1), 0), (w, h), interpolation=cv2.INTER_LINEAR)
    a = alpha[..., None]
    return np.clip(frame * (1 - a) + blurred * a + 0.5, 0, 255).astype(np.uint8)


def pixelate_region(frame: np.ndarray, mask: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Mosaic inside the mask; block size grows with the masked area so faces stay unreadable."""
    alpha = feather(mask) * float(np.clip(strength, 0.0, 1.0))
    if alpha.max() <= 0:
        return frame
    h, w = frame.shape[:2]
    area = float((alpha > 0.5).sum())
    block = int(max(8, round(np.sqrt(max(area, 1.0)) / 8)))
    small = cv2.resize(frame, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    mosaic = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    a = (alpha > 0.15).astype(np.float32)[..., None]  # hard edge: a soft one would leak detail
    return np.clip(frame * (1 - a) + mosaic * a + 0.5, 0, 255).astype(np.uint8)


def apply_effect(frame: np.ndarray, mask: np.ndarray, effect: str, color: str, strength: float) -> np.ndarray:
    if effect == "blur":
        return blur_region(frame, mask, strength)
    if effect == "pixelate":
        return pixelate_region(frame, mask, strength)
    return recolor_frame(frame, mask, color, strength)


def box_mask(shape: tuple[int, int], box, pad: float = 0.12) -> np.ndarray:
    """Soft elliptical mask covering a box (redaction without segmentation)."""
    h, w = shape
    x1, y1, x2, y2 = map(float, box)
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    m = np.zeros((h, w), np.float32)
    center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
    axes = (max(1, int((x2 - x1) / 2 + px)), max(1, int((y2 - y1) / 2 + py)))
    cv2.ellipse(m, center, axes, 0, 0, 360, 1.0, -1)
    return m


class FlowPropagator:
    """Carries masks from one frame to the next with dense optical flow (DIS) on the CPU.

    Between SAM 2 key frames the object's mask follows the real pixel motion (wheels turning, people
    walking) instead of only the tracker box, and a light temporal blend removes flicker. Flow is computed
    once per frame at half resolution and shared by every target."""

    def __init__(self, scale: float = 0.5) -> None:
        self.scale = scale
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        self.prev_gray: np.ndarray | None = None
        self.flow: np.ndarray | None = None  # backward flow: current pixel -> where it was in prev frame

    def step(self, frame: np.ndarray) -> None:
        gray = cv2.cvtColor(cv2.resize(frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA),
                            cv2.COLOR_BGR2GRAY)
        self.flow = self.dis.calc(gray, self.prev_gray, None) if self.prev_gray is not None else None
        self.prev_gray = gray

    def reset(self) -> None:
        self.prev_gray, self.flow = None, None

    def propagate(self, mask: np.ndarray) -> np.ndarray:
        """Warp last frame's mask into the current frame."""
        if self.flow is None:
            return mask
        h, w = mask.shape
        flow = cv2.resize(self.flow, (w, h), interpolation=cv2.INTER_LINEAR) / self.scale
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        return cv2.remap(mask.astype(np.float32), gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def smooth(prev: np.ndarray | None, cur: np.ndarray, keep: float = 0.25) -> np.ndarray:
    """Temporal blend of consecutive masks: less edge flicker, still follows motion."""
    return cur if prev is None or prev.shape != cur.shape else prev * keep + cur * (1 - keep)


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
