"""Collect every t('...') key from the frontend and report which ones ar.json does not translate yet.

    python scripts/i18n_extract.py            # writes frontend/src/i18n/missing.json (keys still to translate)
    python scripts/i18n_extract.py --check    # exit 1 if any key is missing (for CI)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend" / "src"
AR = ROOT / "i18n" / "ar.json"
# t('...') / t("...") / t(`...`) with no ${} inside; first argument only.
CALL = re.compile(r"""\bt\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`([^`$]*)`)""")


def keys() -> list[str]:
    found: set[str] = set()
    for f in ROOT.rglob("*.tsx"):
        for m in CALL.finditer(f.read_text(encoding="utf-8")):
            raw = next(g for g in m.groups() if g is not None)
            found.add(raw.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
                      if "\\" in raw else raw)
    return sorted(found)


def main() -> int:
    all_keys = keys()
    ar = json.loads(AR.read_text(encoding="utf-8")) if AR.exists() else {}
    missing = [k for k in all_keys if k not in ar]
    unused = [k for k in ar if k not in all_keys]
    print(f"{len(all_keys)} keys, {len(missing)} missing in ar.json, {len(unused)} unused")
    if "--check" in sys.argv:
        return 1 if missing else 0
    (ROOT / "i18n" / "missing.json").write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
