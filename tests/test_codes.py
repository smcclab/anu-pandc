import pytest

from anu_pandc import codes


@pytest.mark.parametrize("code,kind", [
    ("COMP1730", "course"),
    ("comp1730", "course"),
    ("MATH1005", "course"),
    ("COMP8900F", "course"),
    ("BCOMP", "program"),
    ("HCOMP", "program"),
    ("7706XMCOMP", "program"),
    ("MMLCV", "program"),
    ("COMS-MAJ", "subplan"),
    ("HCCC-MIN", "subplan"),
    ("ARTIF-SPEC", "subplan"),
    ("MLCV-HSPC", "subplan"),
])
def test_kind_of(code, kind):
    assert codes.kind_of(code) == kind


def test_urls():
    assert codes.url_for("BCOMP", "2026") == "https://programsandcourses.anu.edu.au/2026/program/BCOMP"
    assert codes.url_for("comp1730", "2027") == "https://programsandcourses.anu.edu.au/2027/course/COMP1730"
    assert codes.url_for("COMS-MAJ", "2026") == "https://programsandcourses.anu.edu.au/2026/major/COMS-MAJ"
    assert codes.url_for("HCCC-MIN", "2026") == "https://programsandcourses.anu.edu.au/2026/minor/HCCC-MIN"
    assert codes.url_for("ARTIF-SPEC", "2026").endswith("/2026/specialisation/ARTIF-SPEC")


def test_kind_override():
    # A program whose code happens to look like something else can be forced.
    assert codes.url_for("COMP1730", "2026", "program").endswith("/program/COMP1730")


def test_codes_in_text():
    text = "Take COMP1100 or COMP1130, then the COMS-MAJ or HCCC-MIN. Not ABC12345."
    assert codes.course_codes_in(text) == {"COMP1100", "COMP1130"}
    assert codes.subplan_codes_in(text) == {"COMS-MAJ", "HCCC-MIN"}
