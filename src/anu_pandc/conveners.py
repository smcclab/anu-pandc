"""Who convened what: one row per saved class-summary page.

The convener is published only on class summary pages, so this walks the
``classes/`` directories of a saved tree and emits a table. Name normalisation
strips honorifics and splits multiple names onto "; ". P&C is inconsistent
about some people's names; pass an aliases mapping to collapse them.

Verify a multi-name cell before using it for per-person totals: it can be
genuine co-convening or convener-plus-guest, and the page does not distinguish.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from anu_pandc.store import Store

FIELDS = ["year", "course", "semester", "class_id",
          "convener_raw", "convener_normalized", "lecturer_raw"]

SEMESTER_SHORT = {"FirstSemester": "S1", "SecondSemester": "S2",
                  "SummerSession": "Summer", "AutumnSession": "Autumn",
                  "WinterSession": "Winter", "SpringSession": "Spring"}

TITLES = re.compile(
    r"^\s*(?:Dr|Prof|Professor|AsPr|A/Prof|Assoc\.?\s*Prof\.?|Mr|Ms|Mrs|Miss|"
    r"Emeritus\s+Professor)\.?\s+", re.I)

_FILE_RE = re.compile(r"^([A-Z]{2,4}\d{4}[A-Z]?)-([A-Za-z]+)-(\d+)$")


def load_aliases(path: str | Path | None) -> dict[str, str]:
    """Aliases file: JSON object, or lines of ``Variant = Canonical``."""
    if not path:
        return {}
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return json.loads(text)
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        variant, canonical = (s.strip() for s in line.split("=", 1))
        out[variant] = canonical
    return out


def normalize(raw: str, aliases: dict[str, str] | None = None) -> str:
    aliases = aliases or {}
    names = []
    for part in re.split(r"[,;]", raw or ""):
        n = TITLES.sub("", part).strip()
        if n:
            names.append(aliases.get(n, n))
    return "; ".join(names)


def _field(text: str, name: str) -> str:
    m = re.search(r"\*\*%s:\*\* (.+)" % name, text)
    return m.group(1).strip() if m else ""


def row_from_class_markdown(path: Path, year: str, aliases: dict[str, str] | None = None) -> dict | None:
    m = _FILE_RE.match(path.stem)
    if not m:
        return None
    code, sem_raw, class_id = m.groups()
    text = path.read_text(encoding="utf-8")
    convener = _field(text, "Convener")
    if not convener:
        return None
    return {
        "year": year,
        "course": code,
        "semester": SEMESTER_SHORT.get(sem_raw, sem_raw),
        "class_id": class_id,
        "convener_raw": convener,
        "convener_normalized": normalize(convener, aliases),
        "lecturer_raw": _field(text, "Lecturer"),
    }


def collect(store: Store, prefix: str | None = None, year: str | None = None,
            aliases: dict[str, str] | None = None) -> list[dict]:
    rows = []
    for path in store.class_files(year):
        if prefix and not path.name.startswith(prefix.upper()):
            continue
        row = row_from_class_markdown(path, path.parent.parent.name, aliases)
        if row:
            rows.append(row)
    rows.sort(key=lambda r: (r["year"], r["semester"], r["course"], r["class_id"]))
    return rows


def conveners_to_markdown(rows: list[dict]) -> str:
    lines = [
        "| Year | Course | Semester | Class | Convener | Lecturer |",
        "|------|--------|----------|-------|----------|----------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['year']} | {r['course']} | {r['semester']} | {r['class_id']} | "
            f"{r['convener_normalized']} | {r['lecturer_raw']} |"
        )
    return "\n".join(lines) + "\n"
