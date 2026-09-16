"""Discover every course under a subject prefix via the P&C search API.

Program and subplan pages only name the courses in their requirement lists, so
free electives under a subject area are invisible to a program-driven scrape.
The catalogue search JSON endpoint lists everything for a year, including
Research-career HDR shells (e.g. ``COMP8900F``), which callers usually want
excluded from a teaching-course list.
"""
from __future__ import annotations

from anu_pandc.http import BASE_URL, get

SEARCH_URL = f"{BASE_URL}/data/CourseSearch/GetCourses"
# The API caps the page size regardless of MaxPageSize, so paginate.
PAGE_SIZE = 50

FIELDS = ["code", "title", "career", "units", "sessions"]


def fetch_catalogue(prefix: str, year: str) -> list[dict]:
    """Return all catalogue entries whose CourseCode starts with ``prefix``.

    Each entry is a tidy dict with keys ``code, title, career, units, sessions``
    plus ``raw`` (the API item).
    """
    prefix = prefix.upper()
    items: list[dict] = []
    page = 0
    while True:
        data = get(
            SEARCH_URL,
            params={
                "AppliedFilter": "FilterByCourses",
                "SearchText": prefix,
                "PageIndex": page,
                "MaxPageSize": PAGE_SIZE,
                "SelectedYear": year,
            },
        ).json()
        if not data["Items"]:
            break
        items.extend(data["Items"])
        if len(items) >= data["TotalCount"]:
            break
        page += 1
    # SearchText also matches titles, so filter to the code prefix.
    return [_tidy(i) for i in items if i["CourseCode"].startswith(prefix)]


def _tidy(item: dict) -> dict:
    # Older years (pre-2019) have null Name/Session/Units on some entries.
    units = item.get("Units")
    return {
        "code": item["CourseCode"],
        "title": (item.get("Name") or "").strip() or "(untitled)",
        "career": item.get("Career") or "",
        "units": f"{units:g}" if units is not None else "",
        "sessions": item.get("Session") or "Not offered",
        "raw": item,
    }


def teaching_codes(entries: list[dict], include_research: bool = False) -> set[str]:
    return {e["code"] for e in entries if include_research or e["career"] != "Research"}


def catalogue_to_markdown(entries: list[dict], prefix: str, year: str, scraped_at: str) -> str:
    lines = [
        f"# {prefix} course catalogue {year}",
        "",
        f"- Source: {SEARCH_URL} (SearchText={prefix}, SelectedYear={year})",
        f"- Scraped at: {scraped_at}",
        f"- Courses: {len(entries)}",
        "",
        "| Code | Title | Career | Units | Sessions |",
        "|------|-------|--------|-------|----------|",
    ]
    for e in sorted(entries, key=lambda x: x["code"]):
        lines.append(
            f"| {e['code']} | {e['title']} | {e['career']} | {e['units'] or '?'} | {e['sessions']} |"
        )
    return "\n".join(lines) + "\n"


def catalogue_rows(entries: list[dict]) -> list[dict]:
    """CSV/JSON-friendly rows without the raw API payload."""
    return [{k: e[k] for k in FIELDS} for e in sorted(entries, key=lambda x: x["code"])]
