"""Read the published class timetable (Allocate+ Web Publisher).

https://mytimetable.anu.edu.au is a JavaScript application over a small REST
backend, so the pages are empty until the browser fills them; this talks to the
backend directly.

There are two instances, one per parity of the year: ``/even/`` currently
serves 2026 and ``/odd/`` 2025. There is no year parameter — the instance *is*
the year — so a year that is neither of those cannot be read here at all.

What this is and is not: the *scheduled* timetable, which changes, not evidence
of what was delivered. Required contact hours come from Programs & Courses and
the class summaries; teaching breaks and public holidays come from the
university calendar.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from anu_pandc.http import post

logger = logging.getLogger(__name__)

BASE_URL = "https://mytimetable.anu.edu.au"
ALL_DAYS = ["1", "2", "3", "4", "5", "6", "0"]

#: Activities of this type duplicate a real slot and carry no location.
CLONE_TYPE = "Clone"

_COURSE_CODE = re.compile(r"(?<![A-Z0-9])[A-Z]{4}\d{4}(?![A-Z0-9])")

DAY_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

FIELDS = ["course", "class_number", "period", "group", "activity", "type", "day",
          "start", "end", "duration_min", "sessions", "location", "staff", "co_taught"]


class NoSuchYear(Exception):
    """Only the two instances the Web Publisher runs can be asked about."""


def instance_for(year: str | int) -> str:
    """``even`` or ``odd`` — the Web Publisher instance that holds ``year``."""
    return "even" if int(year) % 2 == 0 else "odd"


def rest_url(year: str | int, path: str) -> str:
    return f"{BASE_URL}/{instance_for(year)}/rest/timetable/{path}"


def fetch_subjects(term: str, year: str | int) -> dict:
    """Raw search response: a dict of offerings keyed like ``COMP3300_S2_1_8682``."""
    url = rest_url(year, "subjects")
    logger.info("[fetch] timetable %s (%s): %s", term, year, url)
    form = [("search-term", term)] + [("days", d) for d in ALL_DAYS] + \
           [("start-time", "00:00"), ("end-time", "23:00")]
    return post(url, data=form).json()


def _end_time(start: str, duration: str) -> str:
    try:
        minutes = int(start[:2]) * 60 + int(start[3:5]) + int(duration)
    except (ValueError, IndexError):
        return ""
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _dates(activity: dict) -> list[date]:
    out = []
    for text in activity.get("activitiesDays") or []:
        try:
            out.append(datetime.strptime(text.strip(), "%d/%m/%Y").date())
        except ValueError:
            continue
    return sorted(out)


def _co_taught(activity: dict, own_code: str) -> str:
    """Other course codes named in the activity description.

    A description reads ``COMP3300_S2_(01)-ComA/01 + COMP6330_S2_(01)-ComA/01``,
    so a code is followed by an underscore — which is a word character, and so
    no word boundary. Hence the explicit lookaround.
    """
    codes = set(_COURSE_CODE.findall(activity.get("description", "")))
    codes.discard(own_code)
    return ", ".join(sorted(codes))


def activities(payload: dict, code: str | None = None, period: str | None = None,
               include_clones: bool = False) -> list[dict]:
    """Flatten a search response into one row per scheduled activity.

    ``Clone`` activities are dropped unless asked for: they duplicate a real
    slot, carry no location, and double every count made over them.
    """
    code = code.upper() if code else None
    rows: list[dict] = []
    for offering_key, offering in payload.items():
        course = offering.get("callista_code") or offering_key.split("_")[0]
        if code and course.upper() != code:
            continue
        class_number = offering_key.rsplit("_", 1)[-1]
        for activity in (offering.get("activities") or {}).values():
            if not include_clones and activity.get("activity_type") == CLONE_TYPE:
                continue
            semester = activity.get("semester_description", "")
            if period and period.lower() not in semester.lower():
                continue
            days = _dates(activity)
            rows.append({
                "course": course,
                "class_number": class_number,
                "period": semester,
                "group": activity.get("activity_group_code", ""),
                "activity": activity.get("activity_code", ""),
                "type": activity.get("activity_type", ""),
                "day": activity.get("day_of_week", ""),
                "start": activity.get("start_time", ""),
                "end": _end_time(activity.get("start_time", ""), activity.get("duration", "0")),
                "duration_min": int(activity.get("duration") or 0),
                "sessions": len(days),
                "location": activity.get("location", ""),
                "staff": activity.get("staff", ""),
                "co_taught": _co_taught(activity, course),
                "dates": [d.isoformat() for d in days],
                "first_date": days[0].isoformat() if days else "",
                "last_date": days[-1].isoformat() if days else "",
                "manager": offering.get("manager", ""),
                "offering": offering_key,
            })
    rows.sort(key=lambda r: (r["course"], r["period"], r["group"], r["activity"]))
    return rows


def student_load(rows: list[dict]) -> list[dict]:
    """Contact hours a single student carries, per activity group.

    Several streams of one group (ComA/01-04) are alternatives — a student
    attends one — so each group contributes one stream, not all of them.
    """
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["course"], row["period"], row["group"]), []).append(row)
    out = []
    for (course, period, group), members in sorted(groups.items()):
        first = members[0]
        out.append({
            "course": course,
            "period": period,
            "group": group,
            "type": first["type"],
            "streams": len(members),
            "minutes_per_week": first["duration_min"],
            "sessions": first["sessions"],
            "total_hours": round(first["duration_min"] * first["sessions"] / 60, 1),
        })
    return out


def sessions_between(rows: list[dict], start: date, end: date) -> list[dict]:
    """The rows that actually run between two dates, with their dates narrowed."""
    out = []
    for row in rows:
        within = [d for d in row["dates"] if start.isoformat() <= d <= end.isoformat()]
        if within:
            out.append({**row, "dates": within, "sessions": len(within),
                        "first_date": within[0], "last_date": within[-1]})
    return out


def rows_for_table(rows: list[dict]) -> list[dict]:
    return [{k: row.get(k, "") for k in FIELDS} for row in rows]


def to_markdown(rows: list[dict], term: str, year: str, scraped_at: str) -> str:
    lines = [f"# Timetable {term} — {year}", "",
             f"- Source: {rest_url(year, 'subjects')} (search-term={term})",
             f"- Scraped at: {scraped_at}",
             f"- Activities: {len(rows)}",
             "- Scheduled, not delivered: the published timetable changes, and it "
             "does not identify teaching staff.", ""]
    managers = sorted({r["manager"] for r in rows if r.get("manager")})
    if managers:
        lines += [f"- Timetable contact: {', '.join(managers)}", ""]

    lines += ["| Course | Class | Period | Group | Act | Type | Day | Start | End | Sessions | Location | Co-taught |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in sorted(rows, key=lambda r: (r["course"], r["period"], r["group"],
                                           DAY_ORDER.get(r["day"], 9), r["start"])):
        lines.append("| {course} | {class_number} | {period} | {group} | {activity} | {type} "
                     "| {day} | {start} | {end} | {sessions} | {location} | {co_taught} |".format(**row))

    load = student_load(rows)
    if load:
        lines += ["", "## Contact hours for one student", "",
                  "One stream per activity group, because alternative streams of a "
                  "group are a choice, not a stack.", "",
                  "| Course | Period | Group | Type | Streams | Min/session | Sessions | Total hours |",
                  "|---|---|---|---|---|---|---|---|"]
        for entry in load:
            lines.append("| {course} | {period} | {group} | {type} | {streams} | "
                         "{minutes_per_week} | {sessions} | {total_hours} |".format(**entry))
    return "\n".join(lines) + "\n"
