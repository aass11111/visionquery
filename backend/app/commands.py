"""One-sentence edit commands, English or Arabic: "make the red car blue", "خلي السيارة الحمراء زرقاء",
"blur the faces", "موه الوجوه". Parsed with rules (CPU only) into object phrase + effect + target colour."""
import re

from .arabic import is_arabic, normalize, stem, translate, vocab
from .schemas import CommandParse

COLOR_HEX = {
    "red": "#ef4444", "orange": "#f97316", "yellow": "#eab308", "green": "#22c55e", "blue": "#3b82f6",
    "purple": "#8b5cf6", "pink": "#ec4899", "brown": "#92400e", "white": "#f8fafc", "gray": "#6b7280",
    "grey": "#6b7280", "black": "#111827", "silver": "#cbd5e1", "gold": "#d4a017", "beige": "#d6c6a5",
    "cyan": "#06b6d4", "teal": "#14b8a6", "navy": "#1e3a8a", "maroon": "#7f1d1d",
}
EN_VERBS = {
    "make": "recolor", "turn": "recolor", "paint": "recolor", "color": "recolor", "colour": "recolor",
    "recolor": "recolor", "recolour": "recolor", "change": "recolor", "dye": "recolor",
    "blur": "blur", "hide": "blur", "mask": "blur", "anonymize": "blur", "anonymise": "blur", "censor": "blur",
    "pixelate": "pixelate", "pixelize": "pixelate",
}
EN_PLURALS = {"cars": "car", "faces": "face", "people": "person", "persons": "person", "buses": "bus",
              "plates": "plate","trucks": "truck", "bikes": "bicycle", "dogs": "dog", "cats": "cat",
              "men": "man", "women": "woman", "children": "child", "kids": "child", "screens": "tv"}
EN_FILLERS = {"the", "a", "an", "to", "into", "in", "all", "every", "please", "color", "colour", "of", "be", "it"}


def _fail(msg: str, effect: str = "recolor", obj: str | None = None) -> CommandParse:
    return CommandParse(ok=False, object=obj, object_en=None, color=None, color_name=None, effect=effect, error=msg)


def parse(text: str) -> CommandParse:
    if is_arabic(text):
        return _parse_arabic(text)
    return _parse_english(text)


def _parse_english(text: str) -> CommandParse:
    words = re.findall(r"#[0-9a-fA-F]{6}|[a-zA-Z]+", text.lower())
    if not words:
        return _fail("Type a command like “make the red car blue”.")
    effect = None
    if words[0] in EN_VERBS:
        effect = EN_VERBS[words.pop(0)]
    if effect is None:
        return _fail("Start with a verb: make / turn / paint / blur / pixelate.")
    color = color_name = None
    if effect == "recolor":
        # The target colour is the last colour word ("make the red car blue" → blue).
        for i in range(len(words) - 1, -1, -1):
            w = words[i]
            if w in COLOR_HEX or w.startswith("#"):
                color_name = w
                color = w if w.startswith("#") else COLOR_HEX[w]
                del words[i]
                break
        if color is None:
            return _fail("Which colour? e.g. “make the red car blue”.", effect)
    obj = " ".join(EN_PLURALS.get(w, w) for w in words if w not in EN_FILLERS)
    if not obj:
        return _fail("Which object? e.g. “make the red car blue”.", effect)
    return CommandParse(ok=True, object=obj, object_en=obj, color=color, color_name=color_name, effect=effect,
                        error=None)


def _parse_arabic(text: str) -> CommandParse:
    v = vocab()
    words = normalize(text).split()
    if not words:
        return _fail("اكتب أمر مثل: خلي السيارة الحمراء زرقاء")
    effect = None
    for i, w in enumerate(words[:3]):  # the verb is one of the first words ("رجاءً خلي…")
        for form in stem(w):
            if form in v["command_verbs"]:
                effect = v["command_verbs"][form]
                words = words[:i] + words[i + 1:]
                break
        if effect:
            break
    if effect is None:
        return _fail("ابدأ بفعل مثل: خلي، لوّن، غيّر، موّه")
    words = [w for w in words if not any(f in v["command_fillers"] for f in stem(w))]

    color = color_name = None
    if effect == "recolor":
        for i in range(len(words) - 1, -1, -1):
            hit = next((v["colors"][f] for f in stem(words[i]) if f in v["colors"]), None)
            if hit:
                color_name, color = hit, COLOR_HEX.get(hit)
                del words[i]
                break
        if color is None:
            return _fail("شنو اللون؟ مثال: خلي السيارة الحمراء زرقاء", effect)
    obj_ar = " ".join(words)
    if not obj_ar:
        return _fail("شنو الشي اللي تريد تغيّره؟", effect)
    obj_en, translated = translate(obj_ar)
    if not translated:
        return _fail(f"ما عرفت هذا الشي: {obj_ar}", effect, obj_ar)
    return CommandParse(ok=True, object=obj_ar, object_en=obj_en, color=color, color_name=color_name,
                        effect=effect, error=None)
