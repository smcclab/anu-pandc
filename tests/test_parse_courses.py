from pathlib import Path
from bs4 import BeautifulSoup
from anu_pandc.parse.courses import parse_course, course_to_markdown

FIXTURES = Path(__file__).parent / "fixtures"


def soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / f"{name}.html").read_text(encoding="utf-8"), "html.parser")


# --- COMP1730 (no prerequisites, has incompatibilities) ---

def test_comp1730_code():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert data["code"] == "COMP1730"


def test_comp1730_title():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert "Programming" in data["title"]


def test_comp1730_units():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert data["units"] == "6"


def test_comp1730_level():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert data["level"] == "1000"


def test_comp1730_has_incompatibilities():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert "COMP1100" in data["incompatibilities"] or "COMP6730" in data["incompatibilities"]


def test_comp1730_learning_outcomes_non_empty():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert len(data["learning_outcomes"]) >= 4
    assert all(len(o) > 5 for o in data["learning_outcomes"])


def test_comp1730_assessment_non_empty():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert len(data["assessment"]) >= 2
    assert all("task" in a for a in data["assessment"])


def test_comp1730_description_non_empty():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert len(data["description"]) > 20


# --- COMP2300 (has prerequisites) ---

def test_comp2300_level():
    data = parse_course(soup("course_COMP2300"), "COMP2300", "https://example.com")
    assert data["level"] == "2000"


def test_comp2300_has_prerequisites():
    data = parse_course(soup("course_COMP2300"), "COMP2300", "https://example.com")
    assert "COMP1730" in data["prerequisites"] or "COMP1100" in data["prerequisites"]


def test_comp2300_prerequisite_codes():
    data = parse_course(soup("course_COMP2300"), "COMP2300", "https://example.com")
    codes = data["prerequisite_codes"]
    assert any(c in codes for c in ["COMP1100", "COMP1130", "COMP1730"])


def test_comp2300_requisite_raw_non_empty():
    data = parse_course(soup("course_COMP2300"), "COMP2300", "https://example.com")
    assert len(data["requisite_raw"]) > 10


def test_comp1730_requisite_raw_non_empty():
    """COMP1730 has incompatibilities but no prerequisites — raw text still captured."""
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert len(data["requisite_raw"]) > 10


def test_comp1730_prerequisite_codes_empty():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    assert data["prerequisite_codes"] == []


# --- Markdown output ---

def test_markdown_heading():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    md = course_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "# COMP1730" in md


def test_markdown_has_learning_outcomes_section():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    md = course_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Learning Outcomes" in md


def test_markdown_has_assessment_section():
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    md = course_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Assessment" in md


def test_markdown_no_llm_text():
    """All learning outcomes in the markdown must appear verbatim in the fixture HTML."""
    data = parse_course(soup("course_COMP1730"), "COMP1730", "https://example.com")
    fixture_text = BeautifulSoup(
        (FIXTURES / "course_COMP1730.html").read_text(encoding="utf-8"),
        "html.parser"
    ).get_text()
    for outcome in data["learning_outcomes"]:
        assert outcome[:30] in fixture_text, f"Outcome not found in source: {outcome[:30]}"


# --- COMP4350 (co-taught, has offerings) ---

def test_comp4350_cotaught():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    assert "COMP8350" in data["cotaught"]


def test_comp4350_cotaught_no_duplicates():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    assert len(data["cotaught"]) == len(set(data["cotaught"]))


def test_comp2300_cotaught():
    """COMP2300 is co-taught with COMP6300."""
    data = parse_course(soup("course_COMP2300"), "COMP2300", "https://example.com")
    assert "COMP6300" in data["cotaught"]


def test_comp4350_offerings_non_empty():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    assert len(data["offerings"]) >= 1


def test_comp4350_offerings_have_year():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    for o in data["offerings"]:
        assert o["year"], "Each offering must have a year"


def test_comp4350_offerings_have_semester():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    for o in data["offerings"]:
        assert o["semester"], "Each offering must have a semester"


def test_comp4350_markdown_cotaught():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    md = course_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "Co-taught with" in md
    assert "COMP8350" in md


def test_comp4350_markdown_offered_in():
    data = parse_course(soup("course_COMP4350"), "COMP4350", "https://example.com")
    md = course_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "Offered in" in md


# --- COMP1100 (offerings include class numbers + class summary URLs) ---

def test_comp1100_offerings_have_class_numbers():
    data = parse_course(soup("course_COMP1100"), "COMP1100", "https://example.com")
    assert any(o["class_number"] for o in data["offerings"])


def test_comp1100_offerings_summary_url_for_current_sem():
    """The Sem 1 2026 row has a 'View' link; future-year rows show 'N/A'."""
    data = parse_course(soup("course_COMP1100"), "COMP1100", "https://example.com")
    sem1_2026 = [
        o for o in data["offerings"]
        if o["year"] == "2026" and o["semester"] == "First Semester"
    ]
    assert sem1_2026, "Expected at least one Sem 1 2026 offering"
    assert sem1_2026[0]["summary_url"] is not None
    assert "/course/COMP1100" in sem1_2026[0]["summary_url"]
    assert sem1_2026[0]["class_number"] == "3695"


def test_comp1100_future_offering_has_no_summary_url():
    """A 2027 row exists but has no class summary link yet."""
    data = parse_course(soup("course_COMP1100"), "COMP1100", "https://example.com")
    future = [o for o in data["offerings"] if o["year"] == "2027"]
    assert future, "Expected at least one 2027 offering"
    assert all(o["summary_url"] is None for o in future)


def test_comp1100_markdown_includes_class_number():
    data = parse_course(soup("course_COMP1100"), "COMP1100", "https://example.com")
    md = course_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "class 3695" in md


# --- Requisite phrasing variants (COMP2610 / MATH1116 style) ---

def _requisite_soup(text: str) -> BeautifulSoup:
    return BeautifulSoup(f'<div class="requisite"><p>{text}</p></div>', "html.parser")


def test_cannot_enrol_phrasing_is_incompatibility():
    data = parse_course(
        _requisite_soup("You cannot enrol in this course if you have completed COMP6261 or ENGN8534."),
        "COMP2610", "https://example.com",
    )
    assert "COMP6261" in data["incompatibilities"]


def test_may_not_enrol_phrasing_is_incompatibility():
    data = parse_course(
        _requisite_soup("You may not enrol in MATH1116 if you have previously completed MATH1014."),
        "MATH1116", "https://example.com",
    )
    assert "MATH1014" in data["incompatibilities"]
