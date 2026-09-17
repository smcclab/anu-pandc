from pathlib import Path

from bs4 import BeautifulSoup

from anu_pandc.offerings import course_from_markdown as _parse_markdown, offerings_to_markdown as _to_markdown, rows_by_year, offerings_to_markdown
from anu_pandc.parse.courses import parse_course, course_to_markdown

FIXTURES = Path(__file__).parent / "fixtures"

# A course page's "Offered in" table carries rows for every future year the class
# schedule has been loaded for, so the parser must keep them all and separate them.
TWO_YEAR_PAGE = """# COMP3430 — Data Wrangling (6 units, Level 3000)

- **URL:** https://programsandcourses.anu.edu.au/2027/course/COMP3430
- **Co-taught with:** COMP8430
- **Offered in:** 2027 Second Semester (In Person, class 10085); \
2028 Second Semester (In Person, class 10846)
"""

NO_OFFERINGS_PAGE = """# COMP8430 — Data Wrangling (6 units, Level 8000)

- **Offered in:** No future offerings found
"""

NO_CLASS_NUMBER_PAGE = """# COMP9999 — Placeholder (6 units, Level 9000)

- **Offered in:** 2028 First Semester
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "COMP3430.md"
    path.write_text(text, encoding="utf-8")
    return path


def soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / f"{name}.html").read_text(encoding="utf-8"),
                         "html.parser")


# --- heading ---

def test_code_from_heading(tmp_path):
    assert _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["code"] == "COMP3430"


def test_title_from_heading(tmp_path):
    assert _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["title"] == "Data Wrangling"


def test_units_from_heading(tmp_path):
    assert _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["units"] == "6"


# --- offerings ---

def test_both_years_kept(tmp_path):
    offerings = _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["offerings"]
    assert [o["year"] for o in offerings] == ["2027", "2028"]


def test_class_numbers_kept_per_year(tmp_path):
    offerings = _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["offerings"]
    assert {o["year"]: o["class_number"] for o in offerings} == {
        "2027": "10085", "2028": "10846"}


def test_mode_parsed(tmp_path):
    offerings = _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["offerings"]
    assert all(o["mode"] == "In Person" for o in offerings)


def test_semester_excludes_the_detail_parenthetical(tmp_path):
    offerings = _parse_markdown(write(tmp_path, TWO_YEAR_PAGE))["offerings"]
    assert all(o["semester"] == "Second Semester" for o in offerings)


def test_no_future_offerings_yields_none(tmp_path):
    assert _parse_markdown(write(tmp_path, NO_OFFERINGS_PAGE))["offerings"] == []


def test_offering_without_class_number(tmp_path):
    offerings = _parse_markdown(write(tmp_path, NO_CLASS_NUMBER_PAGE))["offerings"]
    assert offerings == [{"year": "2028", "semester": "First Semester",
                          "mode": "", "class_number": "", "topic": ""}]


# --- round trip against the writer, so the two cannot drift apart ---

def test_round_trip_from_course_to_markdown(tmp_path):
    data = parse_course(soup("course_COMP1100"), "COMP1100", "https://example.com")
    path = tmp_path / "COMP1100.md"
    path.write_text(course_to_markdown(data, "2026-08-07T00:00:00Z"), encoding="utf-8")

    recovered = _parse_markdown(path)
    assert recovered["code"] == data["code"]
    assert [(o["year"], o["semester"], o["class_number"], o["mode"])
            for o in recovered["offerings"]] == \
           [(o["year"], o["semester"], o["class_number"], o["mode"])
            for o in data["offerings"]]


# --- summary table ---

def test_markdown_pairs_each_semester_with_its_class():
    rows = [
        {"course": "COMP1100", "title": "PaPS", "units": "6",
         "semester": "Second Semester", "class_number": "11051", "mode": "In Person"},
        {"course": "COMP1100", "title": "PaPS", "units": "6",
         "semester": "First Semester", "class_number": "6679", "mode": "In Person"},
    ]
    # S1 must sort before S2 even though its class number is the lower string
    assert "| S1 (6679) / S2 (11051) |" in _to_markdown(rows, "2028", "2027", "COMP")


TOPIC_PAGE = """# COMP4011 — Advanced Topics in Formal Methods (6 units, Level 4000)

- **Offered in:** 2026 Second Semester (In Person, class 9011) — \
Software Verification using Proof Assistant; 2027 Second Semester (In Person, class 10078)
"""


def test_topic_round_trips_through_markdown(tmp_path):
    offerings = _parse_markdown(write(tmp_path, TOPIC_PAGE))["offerings"]
    assert {o["year"]: o["topic"] for o in offerings} == {
        "2026": "Software Verification using Proof Assistant", "2027": ""}
    assert offerings[0]["class_number"] == "9011"
    assert offerings[0]["mode"] == "In Person"


def test_topic_shown_in_offerings_table(tmp_path):
    course = _parse_markdown(write(tmp_path, TOPIC_PAGE))
    rows = rows_by_year([course])["2026"]
    assert rows[0]["topic"] == "Software Verification using Proof Assistant"
    md = offerings_to_markdown(rows, "2026", "2026", "COMP")
    assert "S2 (9011) “Software Verification using Proof Assistant”" in md
