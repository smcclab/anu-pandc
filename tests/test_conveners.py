from anu_pandc.conveners import collect, conveners_to_markdown, load_aliases, normalize
from anu_pandc.store import Store

CLASS_MD = """# COMP1100 — Programming as Problem Solving — First Semester (class 3695)

- **URL:** https://example
- **Convener:** Dr Jane Smith, Prof A. N. Other
- **Lecturer:** Dr Jane Smith
"""


def test_normalize_strips_titles_and_splits():
    assert normalize("Dr Jane Smith, Prof A. N. Other") == "Jane Smith; A. N. Other"


def test_normalize_applies_aliases():
    assert normalize("Tony Hosking", {"Tony Hosking": "Antony Hosking"}) == "Antony Hosking"


def test_load_aliases_lines(tmp_path):
    p = tmp_path / "aliases.txt"
    p.write_text("# comment\nTony Hosking = Antony Hosking\n")
    assert load_aliases(p) == {"Tony Hosking": "Antony Hosking"}


def test_load_aliases_json(tmp_path):
    p = tmp_path / "aliases.json"
    p.write_text('{"A": "B"}')
    assert load_aliases(p) == {"A": "B"}


def test_collect_reads_tree(tmp_path):
    s = Store(tmp_path)
    s.write(s.class_path("2026", "COMP1100", "First Semester", "3695"), CLASS_MD)
    s.write(s.class_path("2026", "MATH1005", "First Semester", "1"), CLASS_MD.replace("COMP1100", "MATH1005"))
    rows = collect(s)
    assert [r["course"] for r in rows] == ["COMP1100", "MATH1005"]
    assert rows[0] == {
        "year": "2026", "course": "COMP1100", "semester": "S1", "class_id": "3695",
        "convener_raw": "Dr Jane Smith, Prof A. N. Other",
        "convener_normalized": "Jane Smith; A. N. Other",
        "lecturer_raw": "Dr Jane Smith",
        "source": "class",
    }
    assert [r["course"] for r in collect(s, prefix="COMP")] == ["COMP1100"]


COURSE_MD = """# COMP4820 — Computing Internship (12 units, Level 4000)

- **URL:** https://example
- **Prerequisites:** None
- **Convener:** Dr Nisansala Yatapanage, Dr Penny Kyburz
- **Offered in:** 2027 First Semester (In Person, class 5099)

## Other Information

Ask the **Convener:** not this line.
"""


def test_collect_falls_back_to_the_course_page(tmp_path):
    s = Store(tmp_path)
    s.write(s.item_path("2027", "course", "COMP4820"), COURSE_MD)
    rows = collect(s)
    assert rows == [{
        "year": "2027", "course": "COMP4820", "semester": "", "class_id": "",
        "convener_raw": "Dr Nisansala Yatapanage, Dr Penny Kyburz",
        "convener_normalized": "Nisansala Yatapanage; Penny Kyburz",
        "lecturer_raw": "", "source": "course",
    }]
    assert "| 2027 | COMP4820 |  |  | Nisansala Yatapanage; Penny Kyburz |  | course |" in conveners_to_markdown(rows)


def test_class_row_wins_over_the_course_page_for_the_same_year(tmp_path):
    s = Store(tmp_path)
    # 2026 has a class summary; 2027 has only the course page.
    s.write(s.class_path("2026", "COMP1100", "First Semester", "3695"), CLASS_MD)
    s.write(s.item_path("2026", "course", "COMP1100"), COURSE_MD.replace("COMP4820", "COMP1100"))
    s.write(s.item_path("2027", "course", "COMP1100"), COURSE_MD.replace("COMP4820", "COMP1100"))
    rows = collect(s)
    assert [(r["year"], r["source"]) for r in rows] == [("2026", "class"), ("2027", "course")]
    assert [(r["year"], r["source"]) for r in collect(s, year="2027")] == [("2027", "course")]


def test_course_without_a_convener_line_gives_no_row(tmp_path):
    s = Store(tmp_path)
    s.write(s.item_path("2027", "course", "COMP1720"),
            "# COMP1720 — Art and Interaction Computing\n\n- **URL:** https://example\n")
    s.write(s.item_path("2027", "course", "MATH1013"), COURSE_MD.replace("COMP4820", "MATH1013"))
    assert collect(s, prefix="COMP") == []
