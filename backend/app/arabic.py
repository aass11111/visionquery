"""Arabic (MSA + Iraqi) search queries → short English phrases the detector understands. CPU only.

Dictionary-based on purpose: no model download, no GPU, instant, and predictable for the vocabulary a video
search needs (objects, colours, attributes, simple relations). Arabic puts adjectives after the noun
("سيارة حمراء"), English before ("red car"), so matched words are re-ordered around each object.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "ar_en.json"
ARABIC = re.compile(r"[؀-ۿ]")
DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat + tatweel
PREFIXES = ("وبال", "وال", "بال", "كال", "فال", "لل", "ال", "و")


def normalize(text: str) -> str:
    """Spelling-insensitive form: no diacritics, unified alef / yaa / taa marbuta, Persian letters mapped."""
    t = DIACRITICS.sub("", text.strip().lower())
    t = re.sub("[أإآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = t.replace("چ", "ج").replace("گ", "ك").replace("ڤ", "ف").replace("پ", "ب").replace("ک", "ك").replace("ی", "ي")
    t = re.sub(r"[^\w\s#]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def stem(word: str) -> list[str]:
    """The word and its forms without a leading article/conjunction ("والسيارة" → "سياره")."""
    forms = [word]
    for p in PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 2:
            forms.append(word[len(p):])
    return forms


@lru_cache(maxsize=1)
def vocab() -> dict[str, dict[str, str]]:
    raw = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    out: dict[str, dict[str, str]] = {}
    for section in ("objects", "colors", "attributes", "connectors", "phrases", "command_verbs", "command_fillers"):
        out[section] = {normalize(k): v for k, v in raw.get(section, {}).items() if normalize(k)}
    return out


def is_arabic(text: str) -> bool:
    return bool(ARABIC.search(text))


def _lookup(words: list[str], i: int) -> tuple[str, str, int] | None:
    """Longest dictionary match starting at word i: (category, english, words consumed)."""
    v = vocab()
    for n in range(min(4, len(words) - i), 0, -1):
        chunk = words[i:i + n]
        variants = {" ".join(chunk)}
        if n == 1:
            variants.update(stem(chunk[0]))
        else:
            variants.add(" ".join([stem(chunk[0])[-1]] + chunk[1:]))
            variants.add(" ".join(stem(w)[-1] for w in chunk))
        for cat in ("phrases", "objects", "colors", "attributes", "connectors"):
            for form in variants:
                if form in v[cat]:
                    return cat, v[cat][form], n
    return None


def translate(text: str) -> tuple[str, bool]:
    """(english, translated). English or mixed input with no Arabic is returned unchanged."""
    if not is_arabic(text):
        return text.strip(), False
    words = normalize(text).split()
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(words):
        hit = _lookup(words, i)
        if hit:
            cat, en, n = hit
            tokens.append((cat, en))
            i += n
        else:
            if not ARABIC.search(words[i]):
                tokens.append(("raw", words[i]))  # numbers or English words mixed in
            i += 1
    if not tokens:
        return text.strip(), False

    # Re-order: Arabic "noun adj adj" → English "adj adj noun"; keep connectors between object groups.
    out: list[str] = []
    group: list[str] = []
    noun: str | None = None

    def flush() -> None:
        nonlocal group, noun
        if noun or group:
            out.append(" ".join(group + ([noun] if noun else [])))
        group, noun = [], None

    for cat, en in tokens:
        if cat in ("objects", "phrases", "raw"):
            if noun:
                flush()
            noun = en
        elif cat in ("colors", "attributes"):
            # Adjectives right after a noun belong to it; colours before attributes, like English.
            if cat == "colors":
                group.insert(0, en)
            else:
                group.append(en)
        else:  # connector
            flush()
            out.append(en)
    flush()
    english = re.sub(r"\s+", " ", " ".join(out)).strip()
    if english.startswith(("with ", "on ", "next to ")):
        english = english.split(" ", 1)[1]
    return english or text.strip(), bool(english)
