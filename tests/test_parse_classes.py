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


# --- every section on the page ------------------------------------------------


def test_every_h2_section_is_captured():
    """Each prose <h2> on a class summary must land in some field.

    A new section ANU adds to the template fails this until it is parsed.
    """
    from anu_pandc.parse.classes import _section_text

    handled_elsewhere = {"class-schedule", "assessment-summary"}
    for name in ("class_COMP1100_FirstSemester_3695", "class_COMP3900_SecondSemester_8846"):
        s = soup(name)
        d = parse_class(s, "X", "P", "1", "u")
        values = [v for v in d.values() if isinstance(v, str) and v]
        for h2 in s.find_all("h2", id=True):
            hid = h2["id"]
            if hid in handled_elsewhere or hid.startswith(("assessmenttask-", "contact_")):
                continue
            if h2.get_text(strip=True) == "Learning Outcomes":
                continue
            text = _section_text(s, hid, h2.get_text(strip=True))
            assert text in values, f"{name}: section {hid!r} not captured"


def test_moderation_of_assessment():
    assert parsed_3900()["moderation_of_assessment"].startswith(
        "Marks that are allocated during Semester are to be considered provisional"
    )


def test_required_and_recommended_resources_kept_apart():
    d = parsed_3900()
    assert d["required_resources"].startswith("You will need to bring a computing device")
    assert d["recommended_resources"].startswith("There are a variety of online platforms")


def test_policies_not_confused_with_learning_outcomes():
    """Both headings share id="policies" on the live page."""
    policies = parsed()["policies"]
    assert policies.startswith("ANU has [educational policies, procedures and guidelines]")
    assert "(https://policies.anu.edu.au/ppl/document/ANUP_000726)" in policies


def test_contacts():
    contacts = parsed_3900()["contacts"]
    assert [c["role"] for c in contacts] == ["Convener", "Instructor"]
    convener = contacts[0]
    assert convener["name"] == "Charles Martin"
    assert convener["email"] == "comp3900@anu.edu.au"
    assert convener["phone"] == "61253139"
    assert convener["consulting_hours"] == ["By Appointment", "Sunday"]
    assert "human-computer interaction" in convener["research_interests"]


def test_contact_without_phone():
    convener = parsed()["contacts"][0]
    assert convener["email"] == "comp1100@anu.edu.au"
    assert convener["phone"] == ""


def test_markdown_renders_new_sections():
    md = class_to_markdown(parsed_3900(), "2026-01-01T00:00:00Z")
    for heading in ("Moderation of Assessment", "Required Resources",
                    "Recommended Resources", "Returning Assignments",
                    "Online Submission", "Staff Feedback", "Contacts", "Policies"):
        assert f"## {heading}" in md
    assert "**Convener:** Charles Martin · comp3900@anu.edu.au · 61253139" in md


# --- markdown in section text -------------------------------------------------


def test_section_links_kept():
    text = parsed()["extensions_and_penalties"]
    assert "[Policy](https://policies.anu.edu.au/ppl/document/ANUP_004603)" in text


def test_section_lists_kept():
    assert "\n- written comments\n- verbal comments" in parsed()["staff_feedback"]


def test_unclosed_bold_does_not_swallow_later_sections():
    """``<b>Timetable webpage.<b></b>`` leaves a <b> open around every later h2."""
    html = """<div>
    <h2 id="tutorial-registration">Tutorial Registration</h2>
    <p>See the <a href="https://mytimetable.anu.edu.au">Timetable</a> <b>Timetable webpage.<b></b>
    <h2 id="assessment-summary">Assessment Summary</h2><p>summary</p>
    <h2 id="participation">Participation</h2><ul><li>Attend</li></ul>
    </div>"""
    d = parse_class(BeautifulSoup(html, "html.parser"), "X", "P", "1", "u")
    # The unclosed <b> wraps the next h2, so it is stepped into rather than
    # rendered: its text survives, its emphasis does not.
    assert d["tutorial_registration"] == (
        "See the [Timetable](https://mytimetable.anu.edu.au) Timetable webpage."
    )
    assert d["participation"] == "- Attend"


def test_task_description_keeps_links_and_lists():
    html = """<div>
    <h2 id="assessmenttask-1">Assessment Task 1</h2>
    <div class="callout-box"><b>Value:</b> 10 %<br/></div>
    <p><b>Quiz (Q)</b></p>
    <p>See the <a href="/course/COMP1100">course page</a>.</p>
    <ul><li>one</li><li>two</li></ul>
    <h2 id="assessmenttask-2">Assessment Task 2</h2>
    </div>"""
    task = parse_class(BeautifulSoup(html, "html.parser"), "X", "P", "1", "u")["assessment_tasks"][0]
    assert task["name"] == "Quiz (Q)"
    assert task["value"] == "10 %"
    assert task["description"] == (
        "See the [course page](https://programsandcourses.anu.edu.au/course/COMP1100).\n\n- one\n- two"
    )
