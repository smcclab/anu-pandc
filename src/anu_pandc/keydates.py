"""Read the ANU University Calendar: census dates, teaching breaks, exams.

The calendar is published twice, as a page and as an iCalendar feed:

``https://www.anu.edu.au/directories/university-calendar?year=YYYY``
    the human page, server-rendered, and the one to cite.
``https://www.anu.edu.au/directories/university-calendar/YYYY/calendar.ics``
    the same dates, machine-readable and near-live.

The feed is read here. Two things about it decide how it is parsed:

*Every event is a single day.* A range is published as separate "begins" and
"ends" (or "commences"/"return") events, so date ranges are paired up rather
than read off a DTEND, which is not there.

*Every DTSTART is midnight UTC* although the date meant is the Canberra local
one. Only the date part is read; converting the timestamp moves the event to
the wrong day.

These are university-wide dates. Course assessment dates come from the class
summaries, and school deadlines live somewhere else entirely.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date

from anu_pandc.http import get

logger = logging.getLogger(__name__)

BASE_URL = "https://www.anu.edu.au/directories/university-calendar"

FIELDS = ["date", "summary", "url"]

# The words that open and close a range, in the order they pair up. Wording
# changes between years, so events are matched on these rather than on whole
# strings.
_RANGE_OPENERS = ("begins", "commences", "starts", "opens", "start of")
_RANGE_CLOSERS = ("ends", "return", "closes", "finishes", "end of")

_UNFOLD = re.compile(r"\r?\n[ \t]")
_EVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.S)


def ics_url(year: str | int) -> str:
    return f"{BASE_URL}/{year}/calendar.ics"


def page_url(year: str | int) -> str:
    return f"{BASE_URL}?year={year}"


def fetch_calendar(year: str | int) -> list[dict]:
    """Every event in a year's calendar, oldest first."""
    url = ics_url(year)
    logger.info("[fetch] calendar %s: %s", year, url)
    return parse_ics(get(url).text)


def parse_ics(text: str) -> list[dict]:
    """Parse the feed into ``{date, summary, url}`` rows."""
    # iCalendar folds long lines by starting the continuation with a space.
    text = _UNFOLD.sub("", text)
    events = []
    for block in _EVENT.findall(text):
        fields = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            name, _, value = line.partition(":")
            fields[name.split(";")[0].strip().upper()] = value.strip()
        stamp = fields.get("DTSTART", "")
        if not re.match(r"\d{8}", stamp):
            continue
        events.append({
            "date": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}",
            "summary": html.unescape(fields.get("SUMMARY", "")).strip(),
            "url": fields.get("URL", ""),
        })
    events.sort(key=lambda e: (e["date"], e["summary"]))
    return events


def find(events: list[dict], *terms: str) -> list[dict]:
    """Events whose summary contains all of ``terms``, case-insensitively."""
    wanted = [t.lower() for t in terms]
    return [e for e in events if all(t in e["summary"].lower() for t in wanted)]


def _normalise(name: str) -> str:
    """A key that survives the calendar's own inconsistencies.

    Between years and between the two halves of one range the wording drifts:
    a hyphen becomes an en dash, an event gains a "New" prefix. Matching on a
    normalised key rather than the literal string keeps the pair together.
    """
    key = re.sub(r"[\u2010-\u2015]", "-", name.lower())
    key = re.sub(r"^new\s*[-:]?\s*", "", key)
    return re.sub(r"[\s\-]+", " ", key).strip()


def _stem(summary: str) -> tuple[str, str | None]:
    """Split a summary into its name and which end of a range it marks.

    "Semester 1 begins" opens a range and "Semester 1 ends" closes it. So does
    "Return from teaching break", which puts its marker at the front, and
    "... period 1 begins (two week duration)", which puts a parenthetical after
    it. "Semester 1 examination period" has no marker at all and is only
    recognisable as an opener once its "ends" partner turns up.
    """
    core = re.sub(r"\s*\([^)]*\)\s*$", "", summary).strip()
    low = core.lower()
    if low.startswith("return from "):
        return core[len("return from "):].strip(), "end"
    for word in _RANGE_OPENERS:
        if low.endswith(" " + word):
            return core[: -len(word)].strip(" -\u2013\u2014"), "start"
    for word in _RANGE_CLOSERS:
        if low.endswith(" " + word):
            return core[: -len(word)].strip(" -\u2013\u2014"), "end"
    return summary, None


def ranges(events: list[dict]) -> list[dict]:
    """Pair the range events up into ``{name, start, end}`` rows.

    An event with no partner stays a single day, because a one-day deadline is
    as real as a range.
    """
    open_rows: dict[str, dict] = {}
    unmarked: dict[str, dict] = {}
    out: list[dict] = []

    for event in events:
        name, edge = _stem(event["summary"])
        key = _normalise(name)
        if edge == "start":
            row = {"name": name, "start": event["date"], "end": "",
                   "url": event["url"], "single_day": False}
            open_rows[key] = row
            out.append(row)
            continue
        if edge == "end":
            row = open_rows.pop(key, None) or unmarked.pop(key, None)
            if row is not None:
                row["end"] = event["date"]
                row["single_day"] = False
                continue
            out.append({"name": name, "start": "", "end": event["date"],
                        "url": event["url"], "single_day": False})
            continue
        row = {"name": name, "start": event["date"], "end": event["date"],
               "url": event["url"], "single_day": True}
        unmarked[key] = row
        out.append(row)

    for row in out:
        if not row["end"]:
            row["end"] = row["start"]
    return out


def between(events: list[dict], start: date, end: date) -> list[dict]:
    return [e for e in events if start.isoformat() <= e["date"] <= end.isoformat()]


def to_markdown(events: list[dict], year: str, scraped_at: str,
                as_ranges: bool = False) -> str:
    lines = [f"# ANU university calendar {year}", "",
             f"- Source: {page_url(year)} (read as {ics_url(year)})",
             f"- Scraped at: {scraped_at}",
             f"- Events: {len(events)}",
             "- University-wide dates only. Course assessment dates are in the "
             "class summaries; check the page before relying on a date.", ""]
    if as_ranges:
        lines += ["| From | To | What |", "|------|----|------|"]
        for row in ranges(events):
            to = "" if row["single_day"] else row["end"]
            lines.append(f"| {row['start']} | {to} | {row['name']} |")
    else:
        lines += ["| Date | Event |", "|------|-------|"]
        for event in events:
            summary = event["summary"]
            if event["url"]:
                summary = f"[{summary}]({event['url']})"
            lines.append(f"| {event['date']} | {summary} |")
    return "\n".join(lines) + "\n"
