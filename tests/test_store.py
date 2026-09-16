from anu_pandc.store import Store, period_slug


def test_paths(tmp_path):
    s = Store(tmp_path)
    assert s.item_path("2026", "program", "BCOMP") == tmp_path / "2026/programs/BCOMP.md"
    assert s.item_path("2026", "subplan", "COMS-MAJ", "json") == tmp_path / "2026/subplans/COMS-MAJ.json"
    assert s.item_path("2026", "course", "COMP1100") == tmp_path / "2026/courses/COMP1100.md"
    assert s.class_path("2026", "COMP1100", "First Semester", "3695") == \
        tmp_path / "2026/classes/COMP1100-FirstSemester-3695.md"
    assert s.table_path("2026", "catalogue", "COMP", "md") == tmp_path / "2026/catalogue-COMP.md"


def test_period_slug():
    assert period_slug("First Semester") == "FirstSemester"
    assert period_slug("Winter Session") == "WinterSession"


def test_merge_codes(tmp_path):
    s = Store(tmp_path)
    assert s.merge_codes("2026", {"COMP1100", "COMP1110"}) == (2, 2)
    assert s.merge_codes("2026", {"COMP1100", "MATH1005"}) == (1, 3)
    assert s.codes_path("2026").read_text() == "COMP1100\nCOMP1110\nMATH1005\n"
    assert s.read_codes("2026") == {"COMP1100", "COMP1110", "MATH1005"}


def test_log_appends(tmp_path):
    s = Store(tmp_path)
    s.log("2026", "one")
    s.log("2026", "two")
    lines = s.log_path("2026").read_text().splitlines()
    assert len(lines) == 2 and lines[1].endswith(" two")


def test_class_files_across_years(tmp_path):
    s = Store(tmp_path)
    for y in ("2025", "2026"):
        s.write(tmp_path / y / "classes" / f"COMP1100-FirstSemester-{y}.md", "x")
    assert [p.parent.parent.name for p in s.class_files()] == ["2025", "2026"]
    assert len(s.class_files("2026")) == 1
