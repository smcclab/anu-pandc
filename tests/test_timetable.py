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


def test_week_of_is_the_monday_to_sunday_around_a_date():
    # Monday 21 September 2026 is the start of its own week, not the end.
    assert timetable.week_of(date(2026, 9, 21)) == (date(2026, 9, 21), date(2026, 9, 27))
    assert timetable.week_of(date(2026, 9, 25)) == (date(2026, 9, 21), date(2026, 9, 27))


def test_a_week_filter_keeps_only_that_week_and_dates_every_row():
    # The failure this exists for: the full table is a weekly pattern with no
    # dates in it, so "what is on in the week of X" cannot be read off it and a
    # reader picks the wrong teaching period. Narrowed to a week, every row
    # carries the dates it actually runs.
    rows = timetable.activities(payload(), "COMP3300")
    lecture = next(r for r in rows if r["group"] == "LecA")
    start, end = timetable.week_of(date.fromisoformat(lecture["first_date"]))
    within = timetable.sessions_between(rows, start, end)
    assert within, "the week of a lecture's first session should not be empty"
    for row in within:
        assert row["first_date"] and row["last_date"]
        assert all(start.isoformat() <= d <= end.isoformat() for d in row["dates"])


def test_the_table_carries_the_dates_each_row_runs():
    rows = timetable.activities(payload(), "COMP3300")
    table = timetable.rows_for_table(rows)
    assert "first_date" in timetable.FIELDS and "last_date" in timetable.FIELDS
    assert all(r["first_date"] for r in table)
    rendered = timetable.to_markdown(rows, "COMP3300", "2026", "2026-01-01T00:00:00Z")
    assert rows[0]["first_date"] in rendered
