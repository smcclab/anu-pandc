"""Fetch-and-parse for the four page types, returning ``Item`` records.

This is the layer the CLI drives. Nothing here writes files; see ``store``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from anu_pandc import codes
from anu_pandc.http import absolute, fetch_page
from anu_pandc.parse.classes import class_to_markdown, parse_class
from anu_pandc.parse.courses import course_to_markdown, parse_course
from anu_pandc.parse.programs import parse_program, program_to_markdown
from anu_pandc.store import now_iso

logger = logging.getLogger(__name__)

_NOT_FOUND_MARKERS = ("page you are looking for doesn't exist", "page you are looking for does not exist")


class PageNotFound(Exception):
    """P&C answers unknown codes with HTTP 200 and a 'doesn't exist' page."""


def _check_found(soup, code: str, url: str) -> None:
    texts = [soup.title.get_text(" ", strip=True) if soup.title else ""]
    texts += [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    texts = [t.lower() for t in texts]
    if "page not found" in texts or any(m in t for t in texts for m in _NOT_FOUND_MARKERS):
        raise PageNotFound(f"{code}: no such page at {url}")


@dataclass
class Item:
    kind: str            # program | subplan | course | class
    code: str
    year: str
    url: str
    data: dict
    scraped_at: str = field(default_factory=now_iso)

    def markdown(self) -> str:
        if self.kind in ("program", "subplan"):
            return program_to_markdown(self.data, self.scraped_at, self.year)
        if self.kind == "course":
            return course_to_markdown(self.data, self.scraped_at)
        return class_to_markdown(self.data, self.scraped_at)

    def json(self) -> str:
        payload = {"kind": self.kind, "year": self.year, "scraped_at": self.scraped_at, **self.data}
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def render(self, fmt: str) -> str:
        return self.json() if fmt == "json" else self.markdown()

    # ---- discovery helpers ---------------------------------------------------

    def course_codes(self) -> set[str]:
        """Course codes referenced by a program/subplan page."""
        return set(self.data.get("all_course_codes", []))

    def subplan_codes(self) -> set[str]:
        """Subplan codes (majors/minors/specialisations) linked from a program page."""
        out: set[str] = set()
        for spec in self.data.get("specialisations", []):
            for entry in spec.get("items", []):
                code = entry.get("code", "")
                if code and codes.kind_of(code) == "subplan":
                    out.add(code)
        return out


def fetch_item(code: str, year: str, kind: str | None = None) -> Item:
    """Fetch and parse a program, subplan or course page."""
    code = codes.normalise(code)
    kind = kind or codes.kind_of(code)
    url = codes.url_for(code, year, kind)
    logger.info("[fetch] %s %s: %s", kind, code, url)
    soup = fetch_page(url)
    _check_found(soup, code, url)
    if kind == "course":
        data = parse_course(soup, code, url)
    else:
        data = parse_program(soup, code, url)
    return Item(kind, code, year, url, data)


def class_targets(course: Item, year: str | None = None, period: str | None = None) -> list[dict]:
    """Offering rows on a course page that have a live class-summary link."""
    return [
        o for o in course.data.get("offerings", [])
        if o.get("summary_url")
        and (year is None or o.get("year") == year)
        and (period is None or o.get("semester") == period)
    ]


def fetch_class(course_code: str, year: str, offering: dict) -> Item:
    """Fetch one class summary page given its offering row from the course page."""
    url = absolute(offering["summary_url"])
    period = offering["semester"]
    class_number = offering["class_number"]
    logger.info("[fetch] class %s %s %s: %s", course_code, period, class_number, url)
    soup = fetch_page(url)
    _check_found(soup, f"{course_code} class {class_number}", url)
    data = parse_class(soup, course_code, period, class_number, url)
    return Item("class", course_code, year, url, data)
