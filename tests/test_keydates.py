from datetime import date
from pathlib import Path

from anu_pandc import keydates

FIXTURES = Path(__file__).parent / "fixtures"


def events():
    return keydates.parse_ics((FIXTURES / "calendar_2026.ics").read_text(encoding="utf-8"))


def test_every_event_is_read():
    assert len(events()) == 55


def test_dates_are_read_as_dates_not_converted_from_utc():
    # DTSTART is midnight UTC but the date meant is the Canberra one, so the
    # date part is taken verbatim. Converting moves census day to the 30th.
    census = keydates.find(events(), "Semester 1", "census")
    assert [e["date"] for e in census] == ["2026-03-31"]


def test_summaries_are_unescaped():
    assert any("New Year's Day" in e["summary"] for e in events())


def test_find_requires_every_term():
    assert keydates.find(events(), "semester 2", "census")
    assert not keydates.find(events(), "semester 2", "nonsense")


def test_ranges_pair_begins_with_ends():
    paired = {row["name"]: row for row in keydates.ranges(events())}
    assert paired["Semester 1"]["start"] == "2026-02-23"
    assert paired["Semester 1"]["end"] == "2026-05-29"


def test_ranges_pair_a_break_with_its_return():
    # "Teaching break commences" is closed by "Return from teaching break",
    # which puts its marker at the front of the summary.
    breaks = [r for r in keydates.ranges(events()) if r["name"] == "Teaching break"]
    assert [(r["start"], r["end"]) for r in breaks] == \
        [("2026-04-06", "2026-04-19"), ("2026-09-07", "2026-09-20")]


def test_a_return_closes_the_range_the_day_before_it():
    # "Return from teaching break" is the first day BACK, not the last day off.
    # Ending the range on it puts the break over the first day of teaching
    # after it: 21 September 2026 is Monday of week 7, a full teaching day.
    breaks = [r for r in keydates.ranges(events()) if r["name"] == "Teaching break"]
    assert [r["resumes"] for r in breaks] == ["2026-04-20", "2026-09-21"]
    assert all(r["end"] < r["resumes"] for r in breaks)


def test_an_ends_event_stays_inclusive():
    # "Semester 1 ends" is the last day of semester, so unlike a return it is
    # the range's own end and carries no resume date.
    sem = next(r for r in keydates.ranges(events()) if r["name"] == "Semester 1")
    assert (sem["start"], sem["end"]) == ("2026-02-23", "2026-05-29")
    assert sem["resumes"] == ""


def test_ranges_pair_an_unmarked_opener_with_its_end():
    # The exam period begins with no "begins" in its summary.
    exams = next(r for r in keydates.ranges(events())
                 if r["name"] == "Semester 1 examination period")
    assert (exams["start"], exams["end"]) == ("2026-06-04", "2026-06-20")


def test_no_range_is_left_half_open():
    assert all(row["start"] and row["end"] for row in keydates.ranges(events()))


def test_single_days_stay_single_days():
    holiday = next(r for r in keydates.ranges(events())
                   if r["name"] == "Canberra Day public holiday")
    assert holiday["single_day"] and holiday["start"] == holiday["end"]


def test_between_filters_by_date():
    within = keydates.between(events(), date(2026, 3, 1), date(2026, 3, 31))
    assert within and all(e["date"].startswith("2026-03") for e in within)


def test_markdown_cites_the_page_not_the_feed():
    rendered = keydates.to_markdown(events(), "2026", "2026-01-01T00:00:00Z")
    assert "university-calendar?year=2026" in rendered
