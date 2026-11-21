from pathlib import Path
from bs4 import BeautifulSoup
from anu_pandc.parse.programs import parse_program, program_to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "program_BCOMP.html"


def soup():
    return BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")


def test_parse_title():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert data["title"] == "Bachelor of Computing"


def test_parse_code_preserved():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert data["code"] == "BCOMP"


def test_parse_url_preserved():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert data["url"] == "https://example.com"


def test_parse_has_course_codes():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    codes = data["all_course_codes"]
    assert len(codes) > 5
    # BCOMP always includes these foundation courses
    assert "COMP1600" in codes or "COMP1730" in codes


def test_parse_course_codes_are_deduplicated():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    codes = data["all_course_codes"]
    assert len(codes) == len(set(codes))


def test_parse_requirements_non_empty():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert len(data["requirements"]) > 0


def test_parse_requirements_have_courses():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    # Requirements are a mix of free-text blocks and course groups. Every
    # 'group' carries a heading; some enumerate courses while others just
    # reference a subject area ("48 units from the subject area COMP"), so
    # only require that the groups collectively pin down some courses.
    groups = [req for req in data["requirements"] if req["type"] == "group"]
    assert len(groups) > 0
    assert all("heading" in req for req in groups)
    assert sum(len(req["courses"]) for req in groups) > 5


def test_parse_specialisations():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    assert len(data["specialisations"]) > 0
    all_types = [s["type"] for s in data["specialisations"]]
    assert any("Major" in t for t in all_types)


def test_markdown_title_line():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "# Bachelor of Computing (BCOMP) 2026" in md


def test_markdown_url_line():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "**URL:** https://example.com" in md


def test_markdown_scraped_line():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "**Scraped:** 2026-01-01T00:00:00Z" in md


def test_markdown_has_specialisations_section():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Specialisations" in md or "## Majors" in md


def test_parse_learning_outcomes():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    outcomes = data["learning_outcomes"]
    assert len(outcomes) == 7
    assert outcomes[0].startswith("Analyse well defined problems")


def test_markdown_has_learning_outcomes_section():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Learning Outcomes" in md
    assert "1. Analyse well defined problems" in md


def test_parse_introduction():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    intro = data["introduction"]
    assert intro
    assert "Bachelor of Computing program" in intro


def test_markdown_has_introduction_section():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00Z")
    assert "## Introduction" in md
    assert "Bachelor of Computing program" in md


# --- admission (the "Admission & Fees" tab) ---

def _admission(name: str = "program_BCOMP") -> dict:
    html = (FIXTURE.parent / f"{name}.html").read_text(encoding="utf-8")
    return parse_program(BeautifulSoup(html, "html.parser"), "X", "https://example.com")["admission"]


def test_admission_ranks():
    adm = _admission()
    assert adm["atar"] == 80
    assert adm["ib"] == 30
    assert adm["ranks"] == {"ATAR": "80", "International Baccalaureate": "30"}


def test_admission_program_with_a_prerequisite_subject():
    adm = _admission()
    assert adm["prerequisite_subjects"]["NSW"] == "HSC Mathematics Advanced or equivalent."
    assert adm["prerequisite_subjects"]["SA/NT"] == "Mathematical Methods or equivalent"
    assert set(adm["prerequisite_subjects"]) == {"ACT", "NSW", "VIC", "QLD", "TAS", "SA/NT", "WA", "IB"}
    assert "NSW: HSC Mathematics Advanced" in adm["sections"]["Prerequisites"]


def test_admission_program_without_a_prerequisite_subject():
    adm = _admission("program_BARTS_2027_admission")
    assert adm["atar"] == 80 and adm["ib"] == 31
    assert adm["prerequisite_subjects"] == {}
    assert "Prerequisites" not in adm["sections"]
    assert list(adm["sections"]) == ["Admission Requirements", "Adjustment Factors"]


def test_admission_sections_keep_the_raw_text_and_stop_at_fees():
    sections = _admission()["sections"]
    assert list(sections) == ["Admission Requirements", "Prerequisites", "Adjustment Factors"]
    text = sections["Admission Requirements"]
    assert text.startswith("At a minimum, all applicants must meet")
    assert "**Domestic applicants**" in text
    # The ATAR box floats inside this section; the fees box follows the last one.
    assert "Baccalaureate" not in text
    assert all("Indicative fee" not in t and "Scholarships" not in t for t in sections.values())


def test_admission_english_policy_link():
    assert _admission()["english_policy_url"] == "https://policies.anu.edu.au/ppl/document/ANUP_000408"


_POSTGRAD = """
<div id="admission-and-fees" class="tab-content"><div class="body__inner w-doublewide copy">
<h2 id="admission-requirements">Admission Requirements</h2>
<p>Applicants must present one of the following:</p>
<ul><li>A Bachelor degree or international equivalent with a minimum GPA of 5.0/7.0</li></ul>
<h2 id="pathways">Pathways</h2><p>GCDP- <a href="/2025/program/6706XGDCP">Graduate Diploma of Computing</a></p>
<div id="indicative-fees" class="callout-box callout-box--right">
  <div class="callout-box__header"><h2 class="callout-box__title">Indicative fees</h2></div>
  <dl><dt>Annual indicative fee for international students</dt><dd>$56,120.00</dd></dl>
</div>
<h2 id="feeInformation">Fee Information</h2><p>All students are required to pay the SA Fee</p>
</div></div>
"""


def test_admission_postgraduate_has_no_ranks():
    adm = parse_program(BeautifulSoup(_POSTGRAD, "html.parser"), "X", "u")["admission"]
    assert adm["atar"] is None and adm["ib"] is None and adm["ranks"] == {}
    assert list(adm["sections"]) == ["Admission Requirements", "Pathways"]
    assert "minimum GPA of 5.0/7.0" in adm["sections"]["Admission Requirements"]
    assert adm["sections"]["Pathways"] == (
        "GCDP- [Graduate Diploma of Computing](https://programsandcourses.anu.edu.au/2025/program/6706XGDCP)")


def test_admission_loose_prerequisites_are_left_as_text():
    # The Diploma of Computing: two jurisdictions in one sentence, not a list.
    html = """<div id="admission-and-fees" class="tab-content">
    <h2 id="admission-requirements">Admission Requirements</h2><p>For admission to this program...</p>
    <h2 id="prerequisites">Prerequisites</h2>
    <p>There are no formal program prerequisites. But assumed knowledge is:</p>
    <ul><li>ACT: Mathematical Methods (Major) or NSW: HSC Mathematics Advanced or equivalent.</li></ul>
    </div>"""
    adm = parse_program(BeautifulSoup(html, "html.parser"), "X", "u")["admission"]
    assert adm["prerequisite_subjects"] == {}
    assert "no formal program prerequisites" in adm["sections"]["Prerequisites"]


def test_admission_absent_on_a_page_without_the_tab():
    html = '<div id="study"><div class="body__inner w-doublewide copy"><p>48 units from</p></div></div>'
    data = parse_program(BeautifulSoup(html, "html.parser"), "COMS-MAJ", "u")
    assert data["admission"] == {}
    assert "Admission" not in program_to_markdown(data | {"title": "T"}, "2026-01-01T00:00:00")


def test_markdown_has_admission_section_after_the_requirements():
    data = parse_program(soup(), "BCOMP", "https://example.com")
    md = program_to_markdown(data, "2026-01-01T00:00:00")
    assert "## Admission Requirements\n\n- **ATAR:** 80\n- **International Baccalaureate:** 30\n" in md
    assert "### Prerequisites\n\nACT: Mathematical Methods" in md
    assert md.index("## Admission Requirements") > md.index("## Minors")
    # The page's own top heading is not repeated as a sub-heading.
    assert "### Admission Requirements" not in md
