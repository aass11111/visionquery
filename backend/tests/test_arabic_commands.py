import pytest

from app.arabic import normalize, translate
from app.commands import parse


@pytest.mark.parametrize("ar, en", [
    ("سيارة حمراء", "red car"),
    ("السيارات البيضاء", "white car"),
    ("شخص يحمل حقيبة", "person with a backpack"),
    ("چلب اسود", "black dog"),
    ("وجوه", "face"),
    ("تكسي", "taxi"),
    ("سيّارة حَمراء", "red car"),  # diacritics
])
def test_translate(ar, en):
    out, translated = translate(ar)
    assert translated and out == en


def test_english_passes_through():
    assert translate("red car") == ("red car", False)


def test_normalize_unifies_spelling():
    assert normalize("أحمر") == normalize("احمر")
    assert normalize("سيارة") == normalize("سياره")


@pytest.mark.parametrize("text, effect, obj, color", [
    ("خلي السيارة الحمراء زرقاء", "recolor", "red car", "blue"),
    ("لوّن الباص اخضر", "recolor", "bus", "green"),
    ("غير لون السيارة البيضاء الى احمر", "recolor", "white car", "red"),
    ("موّه الوجوه", "blur", "face", None),
    ("make the red car blue", "recolor", "red car", "blue"),
    ("blur the faces", "blur", "face", None),
    ("pixelate license plates", "pixelate", "license plate", None),
])
def test_commands(text, effect, obj, color):
    p = parse(text)
    assert p.ok, p.error
    assert (p.effect, p.object_en, p.color_name) == (effect, obj, color)


@pytest.mark.parametrize("text", ["the red car", "make the car", "خلي السيارة", "hello"])
def test_bad_commands_explain_why(text):
    p = parse(text)
    assert not p.ok and p.error
