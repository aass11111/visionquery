import numpy as np

from app.recolor import FlowPropagator, blur_region, box_mask, pixelate_region, smooth


def checker(h=120, w=160, s=8):
    yy, xx = np.mgrid[0:h, 0:w]
    v = (((yy // s) + (xx // s)) % 2 * 255).astype(np.uint8)
    return np.stack([v, v, v], -1)


def test_blur_hides_detail_only_inside_mask():
    frame = checker()
    mask = box_mask((120, 160), (40, 30, 120, 90), pad=0)
    out = blur_region(frame, mask)
    assert out[60, 80].std() < 1 and abs(int(out[60, 80, 0]) - 127) < 60  # centre averaged out
    assert (out[:10, :10] == frame[:10, :10]).all()  # outside untouched


def test_pixelate_makes_blocks():
    frame = checker(s=2)
    mask = np.ones((120, 160), np.float32)
    out = pixelate_region(frame, mask)
    assert len(np.unique(out[40:48, 40:48, 0])) <= 2  # fine 2px detail gone inside a block


def test_flow_moves_mask_with_the_image():
    rng = np.random.default_rng(1)
    a = (rng.random((120, 160, 3)) * 255).astype(np.uint8)
    a = np.repeat(np.repeat(a[::4, ::4], 4, 0), 4, 1)[:120, :160]  # smooth-ish texture
    b = np.roll(a, 6, axis=1)  # whole image moves 6 px right
    mask = np.zeros((120, 160), np.float32)
    mask[40:80, 50:90] = 1
    f = FlowPropagator(scale=1.0)
    f.step(a)
    f.step(b)
    moved = f.propagate(mask)
    xs = np.nonzero(moved[60] > 0.5)[0]
    assert 52 <= xs.min() <= 60 and 92 <= xs.max() <= 100


def test_smooth_blends_previous_mask():
    prev = np.zeros((4, 4), np.float32)
    cur = np.ones((4, 4), np.float32)
    assert np.allclose(smooth(prev, cur, keep=0.25), 0.75)
    assert smooth(None, cur) is cur
