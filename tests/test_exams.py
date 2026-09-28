from pathlib import Path

from bs4 import BeautifulSoup

from anu_pandc import exams

FIXTURES = Path(__file__).parent / "fixtures"


def soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / f"{name}.html").read_text(encoding="utf-8"), "html.parser")


def test_index_lists_the_open_events_with_their_years():
    events = exams.parse_index(soup("exams_index"))
    assert events == [
        {"db": "12", "name": "Semester 2 - In-Class & Online, 2026", "year": "2026"},
        {"db": "13", "name": "Semester 2 - End of Semester, 2026", "year": "2026"},
    ]


def test_event_page_names_itself_and_its_release_state():
    event = exams.parse_event(soup("exams_event_13"), 13)
    assert event["name"] == "Semester 2 - End of Semester, 2026"
    assert event["status"] == "Final Timetable"
    assert event["open"] and not event["closed_after"]


def test_a_closed_event_says_when_it_closed_and_is_not_open():
    # db numbers are recycled slots: 14 held Semester 1 2024.
    event = exams.parse_event(soup("exams_expired_14"), 14)
    assert event["name"] == "Semester 1 - In-Class & Online, 2024"
    assert event["closed_after"] == "2024-05-21"
    assert not event["open"]
    # The apology carries the open list too, which the index parser can read.
    assert [e["db"] for e in exams.parse_index(soup("exams_expired_14"))] == ["12", "13"]


def test_results_are_keyed_by_heading_not_position():
    # An in-class event has no reading time or room column.
    end = exams.parse_results(soup("exams_results_13"))["rows"][0]
    in_class = exams.parse_results(soup("exams_results_12"))["rows"][0]
    assert end["reading_min"] == "15" and end["room"] == "N115-N116"
    assert "reading_min" not in in_class and "room" not in in_class
    assert in_class["writing_min"] == "90"


def test_no_exams_found_is_an_empty_result():
    page = exams.parse_results(soup("exams_none"))
    assert page == {"rows": [], "total": 0, "next": None}


def test_pages_link_forward_until_the_last():
    first = exams.parse_results(soup("exams_COMP_page1"))
    middle = exams.parse_results(soup("exams_COMP_page2"))
    last = exams.parse_results(soup("exams_COMP_page3"))
    assert first["total"] == 58 and len(first["rows"]) == 20
    assert first["next"] == "https://exams.anu.edu.au/timetable/login.php?skip=20"
    # The middle page links back to skip=0 as well; only "Next" is followed.
    assert middle["next"].endswith("skip=40")
    assert last["next"] is None
    assert len(first["rows"]) + len(middle["rows"]) + len(last["rows"]) == 58


def test_combined_exam_codes_name_every_co_taught_course():
    assert exams.courses_of("COMP1110/COMP1140/COMP6710_Semester 2") == [
        "COMP1110", "COMP1140", "COMP6710"]
    # The number after the sitting is not a course.
    assert exams.courses_of("COMP3300_Semester 2 / 3300") == ["COMP3300"]


def test_rooms_fold_into_one_exam_with_date_time_and_end():
    rows = exams.parse_results(soup("exams_results_13"))["rows"]
    folded = exams.exams(rows, {"name": "End of Semester", "db": "13"})
    assert [e["courses"] for e in folded] == [["COMP1730"], ["MATH1014"], ["COMP1100"]]
    comp1730 = folded[0]
    assert len(comp1730["venues"]) == 7
    assert comp1730["date"] == "2026-11-06" and comp1730["day"] == "Fri"
    assert comp1730["start"] == "14:00" and comp1730["end"] == "17:00"
    comp1100 = folded[2]
    # Reading time is part of the sitting.
    assert (comp1100["reading_min"], comp1100["writing_min"]) == (15, 180)
    assert comp1100["end"] == "17:15"
    assert comp1100["event_db"] == "13"


def test_two_sittings_of_one_course_stay_separate():
    rows = exams.parse_results(soup("exams_results_12"))["rows"]
    folded = exams.exams(rows)
    assert [e["date"] for e in folded] == ["2026-08-25", "2026-10-06"]
    assert folded[0]["end"] == "17:30"


def test_full_codes_are_held_to_their_course_and_prefixes_are_not():
    exam_list = [{"courses": ["COMP1100"]}, {"courses": ["COMP11000"]},
                 {"courses": ["COMP1110", "COMP6710"]}, {"courses": []}]
    assert exams.matching(exam_list, ["COMP1100"]) == [exam_list[0], exam_list[3]]
    assert exams.matching(exam_list, ["comp6710"]) == [exam_list[2], exam_list[3]]
    assert exams.matching(exam_list, ["COMP"]) == exam_list


def test_markdown_groups_by_event_and_names_the_status():
    events = [{"db": "12", "name": "In-Class", "status": "Final Timetable", "url": "u12"},
              {"db": "13", "name": "End of Semester", "status": "Final Timetable", "url": "u13"}]
    rows = exams.parse_results(soup("exams_results_13"))["rows"]
    rendered = exams.to_markdown(exams.exams(rows, events[1]), events, ["COMP1100"],
                                 "2026-09-28T00:00:00Z")
    assert "## In-Class\n\nNo exams found." in rendered
    assert "## End of Semester" in rendered
    assert "End of Semester — Final Timetable" in rendered
    assert "| 2026-11-20 | Fri | 14:00 | 17:15 | COMP1100 |" in rendered
