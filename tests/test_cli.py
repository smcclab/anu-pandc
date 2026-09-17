"""End-to-end CLI tests against the saved HTML fixtures (no network)."""
import json
from pathlib import Path

import pytest
import responses as resp
from click.testing import CliRunner

from anu_pandc import http
from anu_pandc.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://programsandcourses.anu.edu.au"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http, "rate_limit_seconds", 0)


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def run(*args):
    return CliRunner().invoke(cli, list(args))


@resp.activate
def test_get_course_prints_markdown():
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1730", body=fixture("course_COMP1730"))
    r = run("get", "comp1730", "--year", "2026", "--plain")
    assert r.exit_code == 0, r.stderr
    assert r.stdout.startswith("# COMP1730 — Programming for Scientists")
    assert "## Learning Outcomes" in r.stdout


@resp.activate
def test_get_course_json():
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1730", body=fixture("course_COMP1730"))
    r = run("get", "COMP1730", "--year", "2026", "--json")
    data = json.loads(r.stdout)
    assert data["kind"] == "course"
    assert data["code"] == "COMP1730"
    assert data["units"] == "6"
    assert data["year"] == "2026"


@resp.activate
def test_get_program_saves_tree_and_codes(tmp_path):
    resp.add(resp.GET, f"{BASE}/2026/program/BCOMP", body=fixture("program_BCOMP"))
    r = run("get", "BCOMP", "--year", "2026", "--save", str(tmp_path), "-f", "md", "-f", "json")
    assert r.exit_code == 0, r.stderr
    md = tmp_path / "2026/programs/BCOMP.md"
    assert md.exists() and (tmp_path / "2026/programs/BCOMP.json").exists()
    assert md.read_text().startswith("# Bachelor of Computing (BCOMP) 2026")
    codes = (tmp_path / "2026/course-codes.txt").read_text().split()
    assert "COMP1100" in codes
    assert (tmp_path / "2026/scrape-log.md").exists()


@resp.activate
def test_get_skips_existing_unless_force(tmp_path):
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1730", body=fixture("course_COMP1730"))
    run("get", "COMP1730", "--year", "2026", "--save", str(tmp_path))
    run("get", "COMP1730", "--year", "2026", "--save", str(tmp_path))
    assert len(resp.calls) == 1
    run("get", "COMP1730", "--year", "2026", "--save", str(tmp_path), "--force")
    assert len(resp.calls) == 2


@resp.activate
def test_get_recursive_walks_program_subplans_courses(tmp_path):
    resp.add(resp.GET, f"{BASE}/2026/program/BCOMP", body=fixture("program_BCOMP"))
    # Every subplan and course the fixture names: serve the same course fixture for all.
    resp.add(resp.GET, resp.matchers.re.compile(rf"{BASE}/2026/(major|minor|specialisation)/.*"),
             body=fixture("program_BCOMP"))
    resp.add(resp.GET, resp.matchers.re.compile(rf"{BASE}/2026/course/.*"),
             body=fixture("course_COMP1100"))
    r = run("get", "BCOMP", "--year", "2026", "--save", str(tmp_path), "--recursive")
    assert r.exit_code == 0, r.stderr
    assert (tmp_path / "2026/programs/BCOMP.md").exists()
    assert list((tmp_path / "2026/subplans").glob("*-MAJ.md"))
    assert (tmp_path / "2026/courses/COMP1100.md").exists()


@resp.activate
def test_get_reports_http_error_and_exits_nonzero():
    resp.add(resp.GET, f"{BASE}/2026/course/COMP9999", status=404)
    r = run("get", "COMP9999", "--year", "2026")
    assert r.exit_code == 1
    assert "COMP9999" in r.stderr


@resp.activate
def test_courses_bulk_from_code_list(tmp_path):
    (tmp_path / "2026").mkdir()
    (tmp_path / "2026/course-codes.txt").write_text("COMP1100\nCOMP1730\nMATH1005\n")
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1100", body=fixture("course_COMP1100"))
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1730", body=fixture("course_COMP1730"))
    r = run("courses", "--year", "2026", "--save", str(tmp_path), "--prefix", "COMP")
    assert r.exit_code == 0, r.stderr
    assert sorted(p.name for p in (tmp_path / "2026/courses").iterdir()) == ["COMP1100.md", "COMP1730.md"]


@resp.activate
def test_classes_fetches_summaries_for_year(tmp_path):
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1100", body=fixture("course_COMP1100"))
    resp.add(resp.GET, resp.matchers.re.compile(rf"{BASE}/course/COMP1100/.*"),
             body=fixture("class_COMP1100_FirstSemester_3695"))
    r = run("classes", "COMP1100", "--year", "2026", "--save", str(tmp_path))
    assert r.exit_code == 0, r.stderr
    files = sorted(p.name for p in (tmp_path / "2026/classes").iterdir())
    assert "COMP1100-FirstSemester-3695.md" in files
    text = (tmp_path / "2026/classes/COMP1100-FirstSemester-3695.md").read_text()
    assert "**Convener:**" in text


@resp.activate
def test_classes_period_filter(tmp_path):
    resp.add(resp.GET, f"{BASE}/2026/course/COMP1100", body=fixture("course_COMP1100"))
    resp.add(resp.GET, resp.matchers.re.compile(rf"{BASE}/course/COMP1100/.*"),
             body=fixture("class_COMP1100_FirstSemester_3695"))
    run("classes", "COMP1100", "--year", "2026", "--period", "Second Semester", "--save", str(tmp_path))
    names = [p.name for p in (tmp_path / "2026/classes").iterdir()] if (tmp_path / "2026/classes").exists() else []
    assert all("SecondSemester" in n for n in names)


CATALOGUE_PAGE = {
    "TotalCount": 2,
    "Items": [
        {"CourseCode": "COMP1100", "Name": "Programming as Problem Solving", "Career": "Undergraduate",
         "Units": 6.0, "Session": "First Semester, Second Semester"},
        {"CourseCode": "COMP8900F", "Name": "Thesis", "Career": "Research", "Units": 24.0, "Session": None},
    ],
}


@resp.activate
def test_catalogue_saves_table_and_merges_teaching_codes(tmp_path):
    resp.add(resp.GET, f"{BASE}/data/CourseSearch/GetCourses", json=CATALOGUE_PAGE)
    r = run("catalogue", "comp", "--year", "2026", "--save", str(tmp_path), "-f", "md", "-f", "csv")
    assert r.exit_code == 0, r.stderr
    assert (tmp_path / "2026/catalogue-COMP.md").read_text().startswith("# COMP course catalogue 2026")
    csv_text = (tmp_path / "2026/catalogue-COMP.csv").read_text()
    assert csv_text.splitlines()[0] == "code,title,career,units,sessions"
    assert "COMP8900F,Thesis,Research,24,Not offered" in csv_text
    # Research shells stay out of the teaching list by default.
    assert (tmp_path / "2026/course-codes.txt").read_text() == "COMP1100\n"


@resp.activate
def test_catalogue_prints_json():
    resp.add(resp.GET, f"{BASE}/data/CourseSearch/GetCourses", json=CATALOGUE_PAGE)
    r = run("catalogue", "COMP", "--year", "2026", "-f", "json")
    assert [e["code"] for e in json.loads(r.stdout)] == ["COMP1100", "COMP8900F"]


def test_offerings_from_saved_tree(tmp_path):
    (tmp_path / "2027/courses").mkdir(parents=True)
    (tmp_path / "2027/courses/COMP3430.md").write_text(
        "# COMP3430 — Data Wrangling (6 units, Level 3000)\n\n"
        "- **Offered in:** 2027 Second Semester (In Person, class 10085); "
        "2028 Second Semester (In Person, class 10846)\n")
    r = run("offerings", "--year", "2027", "--from", str(tmp_path), "--save", str(tmp_path), "--prefix", "COMP")
    assert r.exit_code == 0, r.stderr
    assert (tmp_path / "2027/offerings-COMP.csv").read_text().splitlines() == [
        "course,title,units,semester,class_number,mode,topic",
        "COMP3430,Data Wrangling,6,Second Semester,10085,In Person,"]
    assert "10846" in (tmp_path / "2028/offerings-COMP.csv").read_text()


def test_offerings_prints_csv_by_default(tmp_path):
    (tmp_path / "2027/courses").mkdir(parents=True)
    (tmp_path / "2027/courses/COMP3430.md").write_text(
        "# COMP3430 — Data Wrangling (6 units, Level 3000)\n\n"
        "- **Offered in:** 2027 Second Semester (In Person, class 10085)\n")
    r = run("offerings", "--year", "2027", "--from", str(tmp_path))
    assert r.stdout.splitlines()[0] == "course,title,units,semester,class_number,mode,topic"


def test_conveners_from_tree(tmp_path):
    (tmp_path / "2026/classes").mkdir(parents=True)
    (tmp_path / "2026/classes/COMP1100-FirstSemester-3695.md").write_text(
        "# x\n\n- **Convener:** Dr Jane Smith\n- **Lecturer:** Dr Jane Smith\n")
    r = run("conveners", "--from", str(tmp_path))
    assert r.exit_code == 0, r.stderr
    assert r.stdout.splitlines()[1] == "2026,COMP1100,S1,3695,Dr Jane Smith,Jane Smith,Dr Jane Smith"


def test_url_command():
    r = run("url", "BCOMP", "comp1730", "--year", "2027")
    assert r.stdout.splitlines() == [
        f"{BASE}/2027/program/BCOMP", f"{BASE}/2027/course/COMP1730"]


NOT_FOUND_HTML = """<html><body><h1 class="intro__degree-title">
<span class="intro__degree-title__component">The page you are looking for doesn't exist</span></h1></body></html>"""


@resp.activate
def test_get_unknown_code_is_an_error_not_a_file(tmp_path):
    resp.add(resp.GET, f"{BASE}/2026/course/COMP9999", body=NOT_FOUND_HTML, status=200)
    r = run("get", "COMP9999", "--year", "2026", "--save", str(tmp_path))
    assert r.exit_code == 1
    assert "no such page" in r.stderr
    assert not (tmp_path / "2026/courses/COMP9999.md").exists()
