import json
from datetime import date
from pathlib import Path

from anu_pandc import timetable

FIXTURES = Path(__file__).parent / "fixtures"


def payload():
    return json.loads((FIXTURES / "timetable_COMP3300_2026.json").read_text(encoding="utf-8"))


def test_instance_follows_the_parity_of_the_year():
    assert timetable.instance_for(2026) == "even"
    assert timetable.instance_for("2025") == "odd"
    assert timetable.rest_url(2026, "subjects").endswith("/even/rest/timetable/subjects")


def test_activities_are_flattened_one_row_per_slot():
    rows = timetable.activities(payload(), "COMP3300")
    assert rows
    assert {row["course"] for row in rows} == {"COMP3300"}
    assert {row["class_number"] for row in rows} == {"8682"}


def test_end_time_is_derived_from_the_duration():
    row = next(r for r in timetable.activities(payload(), "COMP3300") if r["group"] == "LecA")
    assert row["start"] == "09:00"
    assert row["duration_min"] == 120
    assert row["end"] == "11:00"


def test_sessions_are_counted_from_the_explicit_dates():
    rows = timetable.activities(payload(), "COMP3300")
    lecture = next(r for r in rows if r["group"] == "LecA")
    assert lecture["sessions"] == len(lecture["dates"]) > 1
    assert lecture["first_date"] < lecture["last_date"]


def test_clone_activities_are_dropped_unless_asked_for():
    kept = timetable.activities(payload(), "COMP3300")
    everything = timetable.activities(payload(), "COMP3300", include_clones=True)
    assert len(everything) >= len(kept)
    assert not [row for row in kept if row["type"] == timetable.CLONE_TYPE]


def test_co_taught_codes_survive_the_trailing_underscore():
    # The description reads COMP3300_S2_(01)-ComA/01 + COMP6330_S2_(01)-ComA/01,
    # so a plain \b word boundary never fires after the code.
    rows = timetable.activities(payload(), "COMP3300")
    assert all(row["co_taught"] == "COMP6330" for row in rows)


def test_period_filter_matches_the_semester_description():
    assert timetable.activities(payload(), "COMP3300", period="Second Semester")
    assert not timetable.activities(payload(), "COMP3300", period="First Semester")


def test_student_load_counts_one_stream_per_group():
    rows = timetable.activities(payload(), "COMP3300")
    load = {entry["group"]: entry for entry in timetable.student_load(rows)}
    # Four computer-lab streams are alternatives; a student attends one.
    assert load["ComA"]["streams"] == 4
    assert load["ComA"]["total_hours"] == 20.0


def test_sessions_between_narrows_the_dates():
    rows = timetable.activities(payload(), "COMP3300")
    lecture = next(r for r in rows if r["group"] == "LecA")
    first = date.fromisoformat(lecture["first_date"])
    within = timetable.sessions_between(rows, first, first)
    assert all(row["sessions"] == 1 for row in within)


def test_markdown_reports_contact_hours_and_says_what_it_is_not():
    rows = timetable.activities(payload(), "COMP3300")
    rendered = timetable.to_markdown(rows, "COMP3300", "2026", "2026-01-01T00:00:00Z")
    assert "## Contact hours for one student" in rendered
    assert "Scheduled, not delivered" in rendered
