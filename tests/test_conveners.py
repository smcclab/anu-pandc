from anu_pandc.conveners import collect, load_aliases, normalize
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
    }
    assert [r["course"] for r in collect(s, prefix="COMP")] == ["COMP1100"]
