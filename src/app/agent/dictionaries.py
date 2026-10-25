import json
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Literal

from app.agent.intake import TEXT_NORMALIZATION

Kind = Literal["symptoms", "medicines"]
STATUS = "starter list, not clinically reviewed"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)


def normalize(text: str) -> str:
    text = text.casefold().translate(TEXT_NORMALIZATION).translate(DIGITS)
    return " ".join(
        "".join(" " if unicodedata.category(char).startswith("P") else char for char in text).split()
    )


def load_file(path: Path) -> list[dict]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError(f"{path.name}: code <unknown>: cannot read valid JSON") from None
    if (
        not isinstance(document, dict)
        or document.get("status") != STATUS
        or not isinstance(document.get("entries"), list)
    ):
        raise ValueError(f"{path.name}: code <unknown>: invalid dictionary document")
    seen = set()
    for entry in document["entries"]:
        code = entry.get("code") if isinstance(entry, dict) else None
        label = code if isinstance(code, str) else "<unknown>"
        reason = ""
        if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9_]+", code):
            reason = "invalid code"
        elif code in seen:
            reason = "duplicate code"
        elif any(
            not isinstance(entry.get(name), str) or not entry[name].strip()
            for name in ("name_fa", "name_en")
        ):
            reason = "names must be non-empty strings"
        elif not isinstance(entry.get("aliases"), list) or any(
            not isinstance(alias, str) or not alias.strip() for alias in entry["aliases"]
        ):
            reason = "aliases must be a list of non-empty strings"
        if reason:
            raise ValueError(f"{path.name}: code {label!r}: {reason}")
        seen.add(code)
    return document["entries"]


@cache
def load_dictionaries() -> dict[Kind, list[dict]]:
    return {kind: load_file(DATA_DIR / f"{kind}.json") for kind in ("symptoms", "medicines")}


def match(kind: Kind, text: str) -> list[dict]:
    haystack = " " + normalize(text) + " "
    found = []
    # ponytail: linear scans suit the small starter lists; index normalized aliases if vocabulary grows.
    for entry in load_dictionaries()[kind]:
        positions = []
        for alias in (entry["name_fa"], entry["name_en"], *entry["aliases"]):
            needle = normalize(alias)
            position = haystack.find(" " + needle + " ") if needle else -1
            if position >= 0:
                positions.append(position)
        if positions:
            found.append((min(positions), entry))
    return [entry for _, entry in sorted(found, key=lambda item: item[0])]


def search(kind: Kind, q: str = "", limit: int = 50) -> list[dict]:
    query = normalize(q)
    return [
        entry for entry in load_dictionaries()[kind]
        if any(query in normalize(alias) for alias in (entry["name_fa"], entry["name_en"], *entry["aliases"]))
    ][:limit]
