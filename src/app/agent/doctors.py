import json
import math
import re
from functools import cache
from pathlib import Path
from typing import get_args

from app.schemas.triage import SpecialtyCode

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "doctors.json"
STATUS = "synthetic demo data, not real doctors"


def load_file(path: Path) -> dict:
    def fail(identifier="<unknown>"):
        raise ValueError(f"{path.name}: id {identifier!r}") from None

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        fail()
    if (
        not isinstance(document, dict) or document.get("status") != STATUS
        or not isinstance(document.get("specialties"), list)
        or not isinstance(document.get("doctors"), list)
    ):
        fail()
    codes = set()
    for specialty in document["specialties"]:
        code = specialty.get("code") if isinstance(specialty, dict) else None
        if (
            not isinstance(code, str) or not re.fullmatch(r"[a-z0-9_]+", code)
            or code in codes or code not in get_args(SpecialtyCode)
            or not nonempty(specialty.get("name_fa")) or not nonempty(specialty.get("name_en"))
        ):
            fail(code if isinstance(code, str) else "<unknown>")
        codes.add(code)
    if codes != set(get_args(SpecialtyCode)):
        fail()
    ids = set()
    for doctor in document["doctors"]:
        identifier = doctor.get("id") if isinstance(doctor, dict) else None
        if (
            not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9_]+", identifier)
            or identifier in ids or not nonempty(doctor.get("name_fa"))
            or not isinstance(doctor.get("specialty_code"), str) or doctor["specialty_code"] not in codes
            or not isinstance(doctor.get("online"), bool)
            or type(doctor.get("score")) not in (int, float)
            or not math.isfinite(doctor["score"]) or not 0 <= doctor["score"] <= 5
            or not isinstance(doctor.get("expertise"), list)
            or not 2 <= len(doctor["expertise"]) <= 3
            or not all(nonempty(item) for item in doctor["expertise"])
        ):
            fail(identifier if isinstance(identifier, str) else "<unknown>")
        ids.add(identifier)
    if not any(doctor["specialty_code"] == "general_practice" for doctor in document["doctors"]):
        fail("general_practice")
    return document


@cache
def load_doctors() -> dict:
    return load_file(DATA_FILE)


def for_specialty(code: str) -> list[dict]:
    return sorted(
        (doctor for doctor in load_doctors()["doctors"] if doctor["specialty_code"] == code),
        key=lambda doctor: (not doctor["online"], -doctor["score"]),
    )[:10]
