from pathlib import Path
from bs4 import BeautifulSoup
from anu_pandc.parse.programs import parse_program, program_to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "program_BCOMP.html"


def soup():
    return BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")


def test_parse_title():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert data["title"] == "Bachelor of Computing"


def test_parse_code_preserved():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert data["code"] == "BCOMP"


def test_parse_url_preserved():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert data["url"] == "https://example.com"


def test_parse_has_course_codes():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    codes = data["all_course_codes"]
    assert len(codes) > 5
    # BCOMP always includes these foundation courses
    assert "COMP1600" in codes or "COMP1730" in codes


def test_parse_course_codes_are_deduplicated():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    codes = data["all_course_codes"]
    assert len(codes) == len(set(codes))


def test_parse_requirements_non_empty():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert len(data["requirements"]) > 0


def test_parse_requirements_have_courses():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    # Requirements are a mix of free-text blocks and course groups. Every
    # 'group' carries a heading; some enumerate courses while others just
    # reference a subject area ("48 units from the subject area COMP"), so
    # only require that the groups collectively pin down some courses.
    groups = [req for req in data["requirements"] if req["type"] == "group"]
    assert len(groups) > 0
    assert all("heading" in req for req in groups)
    assert sum(len(req["courses"]) for req in groups) > 5


def test_parse_specialisations():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert len(data["specialisations"]) > 0
    all_types = [s["type"] for s in data["specialisations"]]
    assert any("Major" in t for t in all_types)


def test_markdown_title_line():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "# Bachelor of Computing (BCOMP) 2026" in md


def test_markdown_url_line():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "**URL:** https://example.com" in md


def test_markdown_scraped_line():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "**Scraped:** 2026-01-01T00:00:00Z" in md


def test_markdown_has_specialisations_section():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Specialisations" in md or "## Majors" in md


def test_parse_learning_outcomes():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    outcomes = data["learning_outcomes"]
    assert len(outcomes) == 7
    assert outcomes[0].startswith("Analyse well defined problems")


def test_markdown_has_learning_outcomes_section():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Learning Outcomes" in md
    assert "1. Analyse well defined problems" in md


def test_parse_introduction():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    intro = data["introduction"]
    assert intro
    assert "Bachelor of Computing program" in intro


def test_markdown_has_introduction_section():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Introduction" in md
    assert "Bachelor of Computing program" in md
