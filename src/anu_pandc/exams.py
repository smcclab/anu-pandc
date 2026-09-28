"""Read the published exam timetable (exams.anu.edu.au).

The Examinations Office publishes each exam *event* — "Semester 2 - End of
Semester, 2026", "Semester 2 - In-Class & Online, 2026" — as its own database
behind one PHP page:

``https://exams.anu.edu.au/timetable/login.php?db=0``
    the index: links to every event open right now, and nothing else.
``https://exams.anu.edu.au/timetable/login.php?db=N``
    one event: a course-code search form, answered by POST to the same URL.

Three things about it decide how it is read:

*An event is only there while it is open.* Nothing is published until the
Examinations Office releases it, and each event closes on a fixed date, after
which its page says "not available after DD/MM/YYYY". So most of the year
there is nothing, or nothing for the period being asked about. The index is
the only way to know what is open; do not guess ``db`` numbers.

*``db`` numbers are recycled slots, not ids.* ``db=14`` is Semester 1 2024,
``db=1`` Semester 1 2025 and ``db=13`` Semester 2 2026. A number says nothing
about the year or period, and the same number will hold a different event
next time around.

*The search and its pages hang off the PHP session.* Results come twenty at a
time, and the "Next 20 Records" link is ``login.php?skip=20`` with no event or
search in it; the server remembers both against the session cookie, which the
shared ``requests`` session carries. The same state is why an event's page
has to be loaded before searching it: once a session has searched one event,
a search posted straight to another answers HTTP 500.

One row of the published table is one exam in one *room*. A large exam fills
several rooms and appears once per room; ``exams()`` folds those back into one
exam with a list of venues.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from anu_pandc.http import fetch_page, post

logger = logging.getLogger(__name__)

BASE_URL = "https://exams.anu.edu.au/timetable/login.php"

#: Guard against a pager that never ends; 58 COMP exams made three pages.
MAX_PAGES = 50

FIELDS = ["event", "courses", "exam_code", "title", "assessment_type", "date", "day",
          "start", "end", "reading_min", "writing_min", "venues"]

# Column headings as published, mapped to row keys. Events differ in which
# columns they carry — an in-class event has no reading time or room — so rows
# are keyed by heading, never by position.
_HEADINGS = {
    "exam code": "exam_code",
    "exam title": "title",
    "assessment type": "assessment_type",
    "date": "date_text",
    "time": "time_text",
    "writing time (minutes)": "writing_min",
    "reading time (minutes)": "reading_min",
    "venue": "venue",
    "building": "building",
    "room": "room",
}

_COURSE_CODE = re.compile(r"[A-Z]{4}\d{4}[A-Z]?")
_EVENT_YEAR = re.compile(r",\s*(\d{4})\s*$")
_CLOSED = re.compile(r"not available after\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)
_RECORDS = re.compile(r"Displaying records\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)", re.I)


def event_url(db: int | str) -> str:
    return f"{BASE_URL}?db={db}"


def _text(node) -> str:
    return " ".join(node.get_text(" ").split()) if node else ""


def _db_of(href: str) -> str | None:
    values = parse_qs(urlsplit(href).query).get("db")
    return values[0] if values else None


def event_year(name: str) -> str:
    """The year an event name ends with: "Semester 2 - End of Semester, 2026" -> "2026"."""
    match = _EVENT_YEAR.search(name)
    return match.group(1) if match else ""


# ---- the index and the event page ---------------------------------------------


def parse_index(soup: BeautifulSoup) -> list[dict]:
    """The events the index links to: ``[{"db", "name", "year"}]``.

    An expired event's page carries the same list under its apology, so this
    reads either. ``db=0`` itself is the index and is not an event.
    """
    events, seen = [], set()
    for link in soup.select("a[href*='login.php?db=']"):
        db = _db_of(link["href"])
        name = _text(link)
        if not db or db == "0" or db in seen or not name:
            continue
        seen.add(db)
        events.append({"db": db, "name": name, "year": event_year(name)})
    return events


def parse_event(soup: BeautifulSoup, db: int | str) -> dict:
    """What one event's page says about itself.

    ``status`` is the release state the page announces beside the name ("Final
    Timetable"); ``closed_after`` is set when the event has shut, and then the
    page has no search form at all.
    """
    content = soup.select_one("div.databee-content") or soup
    headers = [_text(s) for s in content.select("span.blackheader")]
    headers = [h for h in headers if h and h != "Exam Timetables"]
    name = headers[0] if headers else ""
    status = headers[1].lstrip(": ").strip() if len(headers) > 1 else ""
    closed = _CLOSED.search(_text(content))
    closed_after = ""
    if closed:
        closed_after = datetime.strptime(closed.group(1), "%d/%m/%Y").date().isoformat()
    return {
        "db": str(db),
        "name": name,
        "year": event_year(name),
        "status": status,
        "open": content.select_one("form input[name='Code']") is not None and not closed,
        "closed_after": closed_after,
        "url": event_url(db),
    }


def fetch_events() -> list[dict]:
    """Every exam event open right now. Empty most of the year."""
    url = event_url(0)
    logger.info("[fetch] exam events: %s", url)
    return parse_index(fetch_page(url))


def fetch_event(db: int | str) -> dict:
    url = event_url(db)
    logger.info("[fetch] exam event %s: %s", db, url)
    return parse_event(fetch_page(url), db)


# ---- search results -------------------------------------------------------------


def _heading_key(th) -> str:
    text = " ".join(th.get_text(" ").split()).lower()
    return _HEADINGS.get(text, re.sub(r"[^a-z0-9]+", "_", text).strip("_"))


def parse_results(soup: BeautifulSoup) -> dict:
    """One page of search results.

    Returns ``{"rows", "total", "next"}``: the published rows keyed by heading,
    the total the page claims, and the URL of the next page if there is one.
    "Sorry, no exams were found." is an empty result, not an error.
    """
    table = soup.select_one("table#table-compact")
    rows: list[dict] = []
    if table:
        keys = [_heading_key(th) for th in table.select("thead th")]
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            rows.append({key: _text(cell) for key, cell in zip(keys, cells)})
    records = _RECORDS.search(_text(soup))
    next_link = next((a for a in soup.select("a[href*='skip=']")
                      if _text(a).lower().startswith("next")), None)
    return {
        "rows": rows,
        "total": int(records.group(3)) if records else len(rows),
        "next": urljoin(BASE_URL, next_link["href"]) if next_link else None,
    }


def search(db: int | str, terms: list[str]) -> dict:
    """Every published row for these course codes in one event, all pages.

    Returns ``{"event", "rows"}``. The event page is opened before searching,
    as a browser would: once a session has searched one event, a search posted
    straight to another fails with HTTP 500 until that event's page has been
    loaded. The page also says whether the event has closed, in which case
    nothing is searched.

    The server matches each code against the *parts* of a combined exam code,
    case-insensitively and as a prefix: ``COMP6710`` finds
    ``COMP1110/COMP1140/COMP6710_Semester 2``, and ``COMP`` finds every COMP
    exam. A bare number (``6710``) finds nothing.
    """
    url = event_url(db)
    code = ",".join(t.strip() for t in terms if t.strip())
    logger.info("[fetch] exam event %s: %s", db, url)
    form_page = fetch_page(url)
    event = parse_event(form_page, db)
    if not event["open"]:
        return {"event": event, "rows": []}
    form = {"Code": code}
    token = form_page.select_one("form input[name='_token']")
    if token and token.get("value"):
        form["_token"] = token["value"]
    logger.info("[fetch] exam timetable %s (db=%s): %s", code, db, url)
    page = parse_results(BeautifulSoup(post(url, data=form).text, "html.parser"))
    rows = list(page["rows"])
    for _ in range(MAX_PAGES):
        if not page["next"]:
            break
        logger.info("[fetch] exam timetable next page: %s", page["next"])
        page = parse_results(fetch_page(page["next"]))
        rows.extend(page["rows"])
    if rows and len(rows) != page["total"]:
        logger.warning("exam timetable: read %d rows but the page says %d",
                       len(rows), page["total"])
    return {"event": event, "rows": rows}


# ---- turning rows into exams -------------------------------------------------------


def _date(text: str) -> str:
    """ "Friday 20/11/2026" -> "2026-11-20"."""
    match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", text)
    if not match:
        return ""
    return datetime.strptime(match.group(0), "%d/%m/%Y").date().isoformat()


def _time(text: str) -> str:
    """ "2:00pm" -> "14:00"."""
    try:
        return datetime.strptime(text.replace(" ", "").upper(), "%I:%M%p").strftime("%H:%M")
    except ValueError:
        return ""


def _minutes(text: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def _end(day: str, start: str, minutes: int) -> str:
    if not (day and start):
        return ""
    begin = datetime.fromisoformat(f"{day}T{start}")
    return (begin + timedelta(minutes=minutes)).strftime("%H:%M")


def courses_of(exam_code: str) -> list[str]:
    """The course codes in an exam code.

    Co-taught courses sit one exam, published under a combined code:
    ``COMP1110/COMP1140/COMP6710_Semester 2``. What follows the first
    underscore is the sitting, and can carry numbers of its own
    (``COMP3300_Semester 2 / 3300``), so only the part before it is read.
    """
    return _COURSE_CODE.findall(exam_code.split("_", 1)[0].upper())


def _venue(row: dict) -> str:
    venue = row.get("venue", "")
    building = row.get("building", "")
    return f"{venue} (bldg {building})" if venue and building else venue


def exams(rows: list[dict], event: dict | None = None) -> list[dict]:
    """Fold per-room rows into one record per exam, in date order.

    ``end`` is the start plus reading and writing time: when the room is free,
    not when writing stops.
    """
    grouped: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("exam_code", ""), row.get("date_text", ""), row.get("time_text", ""),
               row.get("assessment_type", ""))
        if key not in grouped:
            day = _date(row.get("date_text", ""))
            start = _time(row.get("time_text", ""))
            reading = _minutes(row.get("reading_min"))
            writing = _minutes(row.get("writing_min"))
            grouped[key] = {
                "event": (event or {}).get("name", ""),
                "event_db": (event or {}).get("db", ""),
                "courses": courses_of(row.get("exam_code", "")),
                "exam_code": row.get("exam_code", ""),
                "title": row.get("title", ""),
                "assessment_type": row.get("assessment_type", ""),
                "date": day,
                "day": date.fromisoformat(day).strftime("%a") if day else "",
                "start": start,
                "end": _end(day, start, reading + writing),
                "reading_min": reading,
                "writing_min": writing,
                "venues": [],
                "rooms": [],
            }
        exam = grouped[key]
        venue = _venue(row)
        if venue and venue not in exam["venues"]:
            exam["venues"].append(venue)
            exam["rooms"].append({k: row.get(k, "") for k in ("venue", "building", "room")})
    return sorted(grouped.values(), key=lambda e: (e["date"], e["start"], e["exam_code"]))


def matching(exam_list: list[dict], terms: list[str]) -> list[dict]:
    """Hold full course codes to their exact course.

    The server matches as a prefix, so ``COMP1100`` would also find a
    ``COMP11000``. A term that is a whole course code must equal one of an
    exam's courses; anything shorter (a subject prefix) keeps the prefix
    match. An exam whose code names no course is kept as the server gave it.
    """
    wanted = [t.strip().upper() for t in terms if t.strip()]

    def hit(course: str, term: str) -> bool:
        return course == term if _COURSE_CODE.fullmatch(term) else course.startswith(term)

    return [e for e in exam_list
            if not e["courses"] or any(hit(c, t) for c in e["courses"] for t in wanted)]


def rows_for_table(exam_list: list[dict]) -> list[dict]:
    return [{**{k: e.get(k, "") for k in FIELDS},
             "courses": "/".join(e["courses"]),
             "venues": "; ".join(e["venues"])} for e in exam_list]


def _minutes_text(exam: dict) -> str:
    return f"{exam['writing_min']} + {exam['reading_min']} reading" if exam["reading_min"] \
        else str(exam["writing_min"])


def to_markdown(exam_list: list[dict], events: list[dict], terms: list[str],
                scraped_at: str) -> str:
    term = ", ".join(terms)
    lines = [f"# Exam timetable {term}", "",
             f"- Source: {BASE_URL} (Code={term})",
             f"- Scraped at: {scraped_at}"]
    for event in events:
        state = f" — {event['status']}" if event.get("status") else ""
        lines.append(f"- Event: {event['name']}{state} ({event['url']})")
    lines += [f"- Exams: {len(exam_list)}",
              "- End is start plus reading and writing time. Rooms are as published; "
              "a student sits in one of them, and the timetable does not say which.", ""]
    for event in events:
        mine = [e for e in exam_list if e["event_db"] == event["db"]]
        if len(events) > 1:
            lines += [f"## {event['name']}", ""]
        if not mine:
            lines += ["No exams found.", ""]
            continue
        lines += ["| Date | Day | Start | End | Courses | Title | Type | Minutes | Venues |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for exam in mine:
            lines.append("| {date} | {day} | {start} | {end} | {courses} | {title} "
                         "| {type} | {minutes} | {venues} |".format(
                             date=exam["date"], day=exam["day"], start=exam["start"],
                             end=exam["end"], courses="/".join(exam["courses"]),
                             title=exam["title"], type=exam["assessment_type"],
                             minutes=_minutes_text(exam),
                             venues="<br>".join(exam["venues"])))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def events_to_markdown(events: list[dict], scraped_at: str) -> str:
    lines = ["# Exam timetable events", "",
             f"- Source: {event_url(0)}",
             f"- Scraped at: {scraped_at}",
             "- Only events open right now are listed; each closes on a fixed date.", "",
             "| db | Event | Year |", "|---|---|---|"]
    lines += [f"| {e['db']} | {e['name']} | {e['year']} |" for e in events]
    return "\n".join(lines) + "\n"
