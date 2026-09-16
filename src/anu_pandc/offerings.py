"""Planned offerings (which courses run in which sessions), read off course pages.

A course page's "Offered in" table carries class rows (session, class number,
mode) for *every* future year the class schedule has been loaded for, not just
the page's own year, and it does so long before the per-class summary pages
exist. In August 2026 the 2027 course pages carried 2028 rows while 2028 had no
catalogue and no course pages of its own. Output is therefore split by
*offering* year: one table per year found on the pages.

Rows can come from already-saved course Markdown (fast, offline) or from
freshly fetched pages.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

FIELDS = ["course", "title", "units", "semester", "class_number", "mode"]

# "- **Offered in:** 2027 First Semester (In Person, class 5099); 2028 ..."
_OFFERED_RE = re.compile(r"^- \*\*Offered in:\*\* (.+)$", re.M)
# "# COMP3430 — Data Wrangling (6 units, Level 3000)"
_HEADING_RE = re.compile(
    r"^# (?P<code>[A-Z]{2,4}\d{4}[A-Z]?) — (?P<title>.*?)"
    r"(?:\s*\((?P<units>[\d.]+) units[^)]*\))?\s*$",
    re.M,
)
# "2028 First Semester (In Person, class 6679)" - mode and class are optional
_ENTRY_RE = re.compile(r"^(?P<year>\d{4})\s+(?P<semester>.+?)(?:\s+\((?P<detail>[^)]*)\))?$")

SEMESTER_ORDER = ["Summer Session", "First Semester", "Autumn Session",
                  "Winter Session", "Second Semester", "Spring Session"]
SEMESTER_SHORT = {"Summer Session": "Summer", "First Semester": "S1",
                  "Autumn Session": "Autumn", "Winter Session": "Winter",
                  "Second Semester": "S2", "Spring Session": "Spring"}


def course_from_markdown(path: Path) -> dict:
    """Recover code/title/units/offerings from a saved course Markdown file."""
    text = path.read_text(encoding="utf-8")
    heading = _HEADING_RE.search(text)
    offered_match = _OFFERED_RE.search(text)

    offerings = []
    if offered_match and "No future offerings" not in offered_match.group(1):
        for chunk in offered_match.group(1).split(";"):
            entry = _ENTRY_RE.match(chunk.strip())
            if not entry:
                logger.warning("[skip] unparsed offering in %s: %r", path.name, chunk)
                continue
            mode, class_number = "", ""
            for part in (entry.group("detail") or "").split(","):
                part = part.strip()
                if part.startswith("class "):
                    class_number = part[len("class "):]
                elif part:
                    mode = part
            offerings.append({
                "year": entry.group("year"),
                "semester": entry.group("semester").strip(),
                "mode": mode,
                "class_number": class_number,
            })

    return {
        "code": heading.group("code") if heading else path.stem,
        "title": heading.group("title") if heading else "",
        "units": (heading.group("units") or "") if heading else "",
        "offerings": offerings,
    }


def rows_by_year(courses: list[dict]) -> dict[str, list[dict]]:
    """Flatten parsed course dicts into offering rows, keyed by offering year."""
    out: dict[str, list[dict]] = {}
    for course in courses:
        for o in course.get("offerings", []):
            out.setdefault(o["year"], []).append({
                "course": course["code"],
                "title": course.get("title", ""),
                "units": course.get("units", ""),
                "semester": o.get("semester", ""),
                "class_number": o.get("class_number", ""),
                "mode": o.get("mode", ""),
            })
    for rows in out.values():
        rows.sort(key=lambda r: (r["course"], r["semester"]))
    return out


def _semester_key(name: str) -> tuple[int, str]:
    order = SEMESTER_ORDER.index(name) if name in SEMESTER_ORDER else len(SEMESTER_ORDER)
    return (order, name)


def offerings_to_markdown(rows: list[dict], offering_year: str, source_year: str,
                          prefix: str = "") -> str:
    """One row per course, listing each session it runs in with its class number."""
    by_course: dict[str, dict] = {}
    for row in rows:
        entry = by_course.setdefault(row["course"], {
            "title": row["title"], "units": row["units"], "sittings": []})
        entry["sittings"].append((row["semester"], row["class_number"]))

    label = f"{prefix} planned offerings" if prefix else "Planned offerings"
    lines = [
        f"# {label} {offering_year}",
        "",
        f"- Source: {source_year} course pages on Programs & Courses "
        f"(the `Offered in` table), which carry {offering_year} class rows",
        f"- Courses: {len(by_course)} — offering rows: {len(rows)}",
        "",
        "| Code | Title | Units | Sittings |",
        "|------|-------|-------|----------|",
    ]
    for code in sorted(by_course):
        entry = by_course[code]
        sittings = sorted(set(entry["sittings"]), key=lambda s: (_semester_key(s[0]), s[1]))
        rendered = " / ".join(
            f"{SEMESTER_SHORT.get(sem, sem)} ({cls})" if cls else SEMESTER_SHORT.get(sem, sem)
            for sem, cls in sittings
        )
        lines.append(f"| {code} | {entry['title']} | {entry['units']} | {rendered} |")
    return "\n".join(lines) + "\n"
