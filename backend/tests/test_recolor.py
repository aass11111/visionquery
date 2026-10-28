import numpy as np

from app.recolor import clip_to_box, hex_to_bgr, iou, recolor_frame, warp_mask


def test_hex_to_bgr():
    assert hex_to_bgr("#ff8000") == (0, 128, 255)


def test_recolor_only_touches_mask_and_shifts_hue():
    frame = np.full((100, 100, 3), (40, 40, 200), np.uint8)  # red in BGR
    mask = np.zeros((100, 100), np.float32)
    mask[30:70, 30:70] = 1
    out = recolor_frame(frame, mask, "#0000ff", 1.0)
    assert (out[0:5, 0:5] == frame[0:5, 0:5]).all()  # background untouched
    b, g, r = out[50, 50].astype(int)
    assert b > r  # centre turned blue


def test_recolor_strength_zero_is_identity():
    frame = np.random.default_rng(0).integers(0, 255, (40, 40, 3), dtype=np.uint8)
    out = recolor_frame(frame, np.ones((40, 40), np.float32), "#00ff00", 0.0)
    assert (out == frame).all()


def test_warp_mask_follows_box():
    mask = np.zeros((100, 100), np.float32)
    mask[10:30, 10:30] = 1
    moved = warp_mask(mask, (10, 10, 30, 30), (50, 50, 90, 90))
    ys, xs = np.nonzero(moved > 0.5)
    assert 49 <= xs.min() <= 51 and 88 <= xs.max() <= 90
    assert moved[:40, :40].sum() == 0


def test_clip_and_iou():
    m = np.ones((10, 10), np.float32)
    assert clip_to_box(m, (2, 2, 5, 5), pad=0).sum() == 9
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0
