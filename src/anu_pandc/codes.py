"""Classify Programs & Courses codes and build their URLs.

P&C uses three code shapes, each with its own URL scheme:

* courses:   ``COMP1100``, ``MATH1005``, ``COMP8900F``
             -> /<year>/course/<code>
* subplans:  ``COMS-MAJ``, ``HCCC-MIN``, ``ARTIF-SPEC``, ``MLCV-HSPC``
             -> /<year>/major|minor|specialisation/<code>
* programs:  anything else - ``BCOMP``, ``7706XMCOMP``, ``MMLCV``
             -> /<year>/program/<code>

Detection is by shape, so a user can hand ``anu-pandc get`` any code and get
the right page. ``--kind`` on the CLI overrides it for the odd case that
does not fit.
"""
from __future__ import annotations

import re

from anu_pandc.http import BASE_URL

Kind = str  # "program" | "subplan" | "course"

COURSE_CODE_RE = re.compile(r"^[A-Z]{2,4}\d{4}[A-Z]?$")
# Matches a course code anywhere in text.
COURSE_CODE_IN_TEXT_RE = re.compile(r"\b([A-Z]{2,4}\d{4}[A-Z]?)\b")
SUBPLAN_SUFFIXES = {
    "MAJ": "major",
    "MIN": "minor",
    "SPEC": "specialisation",
    "HSPC": "specialisation",
    "SPC": "specialisation",
}
SUBPLAN_CODE_RE = re.compile(
    r"\b([A-Z]{2,8}-(?:" + "|".join(SUBPLAN_SUFFIXES) + r"))\b"
)


def normalise(code: str) -> str:
    return code.strip().upper()


def kind_of(code: str) -> Kind:
    """Return 'course', 'subplan' or 'program' for a P&C code."""
    code = normalise(code)
    if COURSE_CODE_RE.match(code):
        return "course"
    if "-" in code and code.rsplit("-", 1)[1] in SUBPLAN_SUFFIXES:
        return "subplan"
    return "program"


def subplan_type(code: str) -> str:
    """'major', 'minor' or 'specialisation' from a subplan code's suffix."""
    suffix = normalise(code).rsplit("-", 1)[-1]
    return SUBPLAN_SUFFIXES.get(suffix, "specialisation")


def url_for(code: str, year: str, kind: Kind | None = None) -> str:
    code = normalise(code)
    kind = kind or kind_of(code)
    if kind == "course":
        return f"{BASE_URL}/{year}/course/{code}"
    if kind == "subplan":
        return f"{BASE_URL}/{year}/{subplan_type(code)}/{code}"
    return f"{BASE_URL}/{year}/program/{code}"


def program_url(code: str, year: str) -> str:
    return url_for(code, year, "program")


def course_url(code: str, year: str) -> str:
    return url_for(code, year, "course")


def subplan_url(code: str, year: str) -> str:
    return url_for(code, year, "subplan")


def course_codes_in(text: str) -> set[str]:
    return set(COURSE_CODE_IN_TEXT_RE.findall(text))


def subplan_codes_in(text: str) -> set[str]:
    return set(SUBPLAN_CODE_RE.findall(text))
