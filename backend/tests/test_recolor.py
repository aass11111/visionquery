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


def test_white_lettering_on_coloured_object_stays_white():
    frame = np.full((100, 100, 3), (200, 90, 30), np.uint8)  # blue bus (BGR)
    frame[45:55, 20:80] = (245, 245, 245)  # white lettering
    mask = np.ones((100, 100), np.float32)
    out = recolor_frame(frame, mask, "#22c55e", 1.0)
    b, g, r = out[30, 50].astype(int)
    assert g > b and g > r  # the paint turned green
    lb, lg, lr = out[50, 50].astype(int)
    assert min(lb, lg, lr) > 215 and max(lb, lg, lr) - min(lb, lg, lr) < 20  # lettering still white


def test_bus_with_mostly_glass_and_lettering_keeps_neutrals():
    # Like the real bus: 45% dark windows, 20% white lettering, 35% blue paint.
    frame = np.full((100, 100, 3), (200, 90, 30), np.uint8)
    frame[:45] = (40, 35, 30)
    frame[45:65] = (245, 245, 245)
    out = recolor_frame(frame, np.ones((100, 100), np.float32), "#22c55e", 1.0)
    b, g, r = out[80, 50].astype(int)
    assert g > b and g > r  # paint turned green
    assert np.abs(out[55, 50].astype(int) - 245).max() < 20  # lettering still white
    assert np.abs(out[20, 50].astype(int) - frame[20, 50].astype(int)).max() < 15  # glass untouched


def test_white_object_is_recoloured():
    frame = np.full((100, 100, 3), (235, 235, 235), np.uint8)  # white car
    mask = np.zeros((100, 100), np.float32)
    mask[20:80, 20:80] = 1
    out = recolor_frame(frame, mask, "#ef4444", 1.0)
    b, g, r = out[50, 50].astype(int)
    assert r > g + 40 and r > b + 40  # it turned red


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
