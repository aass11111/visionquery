import numpy as np

from app.suggest import color_name, summarize


def solid(bgr):
    return np.full((60, 60, 3), bgr, np.uint8)


def test_color_names():
    assert color_name(solid((30, 30, 220))) == "red"
    assert color_name(solid((220, 60, 30))) == "blue"
    assert color_name(solid((40, 200, 40))) == "green"
    assert color_name(solid((30, 220, 230))) == "yellow"
    assert color_name(solid((245, 245, 245))) == "white"
    assert color_name(solid((15, 15, 15))) == "black"
    assert color_name(solid((128, 128, 128))) == "gray"
    assert color_name(solid((20, 60, 100))) == "brown"


def test_summarize_orders_by_presence_and_adds_colours():
    dets = [(f, "car", "red") for f in range(0, 50, 5)] + [(0, "car", "white"), (5, "car", "white"),
                                                            (10, "person", "blue"), (20, "person", None)]
    items = summarize(dets, frames_sampled=10)
    labels = [i["label"] for i in items]
    assert labels[0] == "car"
    assert labels[1:3] == ["red car", "white car"]
    assert "person" in labels and "blue person" not in labels  # people aren't "coloured" queries
