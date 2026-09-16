from pathlib import Path
from bs4 import BeautifulSoup
from anu_pandc.parse.classes import (
    parse_class,
    class_to_markdown,
    _extract_type_code,
)

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://programsandcourses.anu.edu.au/course/COMP1100/First%20Semester/3695"


def soup(name: str) -> BeautifulSoup:
    return BeautifulSoup(
        (FIXTURES / f"{name}.html").read_text(encoding="utf-8"), "html.parser"
    )


def parsed():
    return parse_class(
        soup("class_COMP1100_FirstSemester_3695"),
        "COMP1100",
        "First Semester",
        "3695",
        URL,
    )


# --- header / metadata --------------------------------------------------------


def test_title_extracted():
    assert "Programming as Problem Solving" in parsed()["title"]


def test_convener_present():
    convener = parsed()["convener"]
    assert isinstance(convener, list)
    assert any("Pattinson" in c for c in convener)


def test_class_dates():
    d = parsed()
    assert d["class_start_date"] == "23/02/2026"
    assert d["class_end_date"] == "29/05/2026"
    assert d["census_date"] == "31/03/2026"


def test_mode_and_units():
    d = parsed()
    assert d["mode"] == "In Person"
    assert "6" in d["units"]


# --- learning outcomes --------------------------------------------------------


def test_learning_outcomes_count():
    los = parsed()["learning_outcomes"]
    assert len(los) == 6
    assert all(len(lo) > 5 for lo in los)


# --- assessment summary -------------------------------------------------------


def test_assessment_summary_has_five_items():
    assert len(parsed()["assessment_summary"]) == 5


def test_assessment_summary_has_final_exam():
    summary = parsed()["assessment_summary"]
    exam = next((s for s in summary if s["type_code"] == "E"), None)
    assert exam is not None
    assert "Final Exam" in exam["task"]
    assert "55" in exam["weight"]


def test_assessment_summary_has_midterm_test():
    summary = parsed()["assessment_summary"]
    mid = next((s for s in summary if s["type_code"] == "M"), None)
    assert mid is not None
    assert "Mid-Term Test" in mid["task"]


def test_assessment_summary_due_dates():
    summary = parsed()["assessment_summary"]
    a1 = next((s for s in summary if s["type_code"] == "A1"), None)
    assert a1 is not None
    assert a1["due_date"] == "10/04/2026"


def parsed_3900():
    return parse_class(
        soup("class_COMP3900_SecondSemester_8846"),
        "COMP3900",
        "Second Semester",
        "8846",
        "https://programsandcourses.anu.edu.au/course/COMP3900/Second%20Semester/8846",
    )


def test_return_of_assessment_column_not_mistaken_for_los():
    """When the table has a 'Return of assessment' column, LOs must still be LOs."""
    summary = parsed_3900()["assessment_summary"]
    a1 = next(s for s in summary if s["task"].startswith("Assignment 1"))
    assert a1["due_date"] == "18/08/2025"
    assert a1["return_date"] == "02/09/2025"
    assert a1["learning_outcomes"] == "1, 2"


def test_return_of_assessment_absent_for_four_column_table():
    summary = parsed()["assessment_summary"]
    assert all(s.get("return_date", "") == "" for s in summary)


def test_return_of_assessment_in_task_callout():
    tasks = parsed_3900()["assessment_tasks"]
    a1 = next(t for t in tasks if t["name"].startswith("Assignment 1"))
    assert a1["return_date"] == "02/09/2025"


def test_markdown_return_column_rendered():
    md = class_to_markdown(parsed_3900(), "2026-01-01T00:00:00Z")
    assert "| Task | Type | Weight | Due Date | Return | LOs |" in md
    assert "Return: 02/09/2025" in md


def test_extract_type_code():
    assert _extract_type_code("Final Exam (E)") == "E"
    assert _extract_type_code("Programming Assignment 1 (A1)") == "A1"
    assert _extract_type_code("Participation (P)") == "P"
    assert _extract_type_code("Some Task With No Code") == ""


# --- per-task assessment details ----------------------------------------------


def test_assessment_tasks_match_summary():
    d = parsed()
    assert len(d["assessment_tasks"]) == len(d["assessment_summary"])


def test_final_exam_task_value():
    tasks = parsed()["assessment_tasks"]
    final = next(t for t in tasks if t["type_code"] == "E")
    assert "55" in final["value"]
    assert "hurdle" in final["description"].lower()


# --- examinations & participation --------------------------------------------


def test_examinations_section_non_empty():
    text = parsed()["examinations"]
    assert "exam" in text.lower()
    assert len(text) > 50


def test_participation_section_non_empty():
    assert "Participation" in parsed()["participation"]


# --- late submission & extensions --------------------------------------------


def test_late_submission_section_extracted():
    text = parsed()["late_submission"]
    assert "late submission" in text.lower()
    assert "not permitted" in text.lower()


def test_extensions_and_penalties_section_extracted():
    text = parsed()["extensions_and_penalties"]
    assert "extension" in text.lower()
    assert "Student Assessment" in text


def test_late_submission_rendered_in_markdown():
    md = class_to_markdown(parsed(), "2026-05-08T00:00:00Z")
    assert "## Late Submission" in md
    assert "## Extensions and Penalties" in md


# --- class schedule -----------------------------------------------------------


def test_class_schedule_rows():
    rows = parsed()["class_schedule"]
    assert len(rows) >= 12
    assert all(r["week"] for r in rows)


# --- markdown render ----------------------------------------------------------


def test_markdown_heading():
    md = class_to_markdown(parsed(), "2026-05-08T00:00:00Z")
    assert "# COMP1100" in md
    assert "First Semester" in md
    assert "class 3695" in md


def test_markdown_assessment_summary_section():
    md = class_to_markdown(parsed(), "2026-05-08T00:00:00Z")
    assert "## Assessment Summary" in md
    assert "Final Exam" in md
    assert "55 %" in md


def test_markdown_examinations_section():
    md = class_to_markdown(parsed(), "2026-05-08T00:00:00Z")
    assert "## Examination(s)" in md


def test_markdown_no_llm_text():
    """Each LO in the markdown must appear in the source HTML."""
    d = parsed()
    fixture_text = (
        FIXTURES / "class_COMP1100_FirstSemester_3695.html"
    ).read_text(encoding="utf-8")
    fixture_text = BeautifulSoup(fixture_text, "html.parser").get_text()
    for outcome in d["learning_outcomes"]:
        assert outcome[:30] in fixture_text
