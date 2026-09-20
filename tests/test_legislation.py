import json
from pathlib import Path

import pytest
import responses as resp

from anu_pandc import http, legislation

FIXTURES = Path(__file__).parent / "fixtures"
API = "https://api.prod.legislation.gov.au/v1/titles"


def unquoted(url: str) -> str:
    from urllib.parse import unquote_plus
    return unquote_plus(url)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http, "rate_limit_seconds", 0)


def title_json():
    return json.loads((FIXTURES / "legislation_F2024L01752_title.json").read_text(encoding="utf-8"))


def register_title():
    resp.add(resp.GET, API, json=title_json())


def register_text():
    resp.add(resp.GET,
             legislation.text_url("F2024L01752", "2024-12-24"),
             body=(FIXTURES / "legislation_F2024L01752_text.html").read_text(encoding="utf-8"),
             content_type="text/html")


def test_a_register_id_needs_no_lookup():
    assert legislation.resolve("F2024L01752") == "F2024L01752"
    assert legislation.resolve("see c2004a04206 for the Act") == "C2004A04206"


@resp.activate
def test_a_name_is_resolved_through_the_register():
    register_title()
    assert legislation.resolve("Coursework Awards Rule") == "F2024L01752"
    assert "contains(name,'Coursework Awards Rule')" in unquoted(resp.calls[0].request.url)


@resp.activate
def test_search_escapes_a_quote_in_the_term():
    resp.add(resp.GET, API, json={"value": []})
    legislation.search_titles("King's Birthday")
    assert "contains(name,'King''s Birthday')" in unquoted(resp.calls[0].request.url)


@resp.activate
def test_missing_title_is_an_error_not_an_empty_dict():
    resp.add(resp.GET, API, json={"value": []})
    with pytest.raises(legislation.NoSuchTitle):
        legislation.fetch_title("F9999L99999")


@resp.activate
def test_instrument_carries_status_and_what_authorises_it():
    register_title()
    register_text()
    data = legislation.fetch_instrument("F2024L01752")
    assert data["name"] == "Coursework Awards Rule 2024"
    assert data["kind"] == "Rules"
    assert data["in_force"] is True
    # Made under the Governance Statute, which is how ANU rules hang together.
    assert data["authorised_by"] == ["F2024L00724"]


@resp.activate
def test_text_url_is_built_from_the_version_start_date():
    register_title()
    register_text()
    data = legislation.fetch_instrument("F2024L01752")
    assert data["version_start"] == "2024-12-24"
    assert data["text_url"] == legislation.text_url("F2024L01752", "2024-12-24")


@resp.activate
def test_body_is_readable_prose_not_mojibake():
    register_title()
    register_text()
    body = legislation.fetch_instrument("F2024L01752")["body"]
    assert "Coursework Awards Rule 2024" in body
    # The Register sends no charset, so a naive decode turns every em dash into
    # "â€”" and every name with an accent into nonsense.
    assert "â" not in body
    assert "Part 1— Preliminary" in body


@resp.activate
def test_contents_dot_leaders_are_collapsed():
    register_title()
    register_text()
    assert "........." not in legislation.fetch_instrument("F2024L01752")["body"]


@resp.activate
def test_markdown_states_status_and_links_the_authorising_instrument():
    register_title()
    register_text()
    rendered = legislation.instrument_to_markdown(
        legislation.fetch_instrument("F2024L01752"), "2026-01-01T00:00:00Z")
    assert "- **Status:** InForce (in force)" in rendered
    assert "F2024L00724" in rendered


@resp.activate
def test_anu_index_is_grouped_and_skips_the_related_links():
    resp.add(resp.GET, legislation.ANU_INDEX_URL,
             body=(FIXTURES / "legislation_anu_index.html").read_text(encoding="utf-8"),
             content_type="text/html; charset=utf-8")
    rows = legislation.fetch_anu_index()
    sections = {row["section"] for row in rows}
    assert {"Acts", "Statutes", "Rules"} <= sections
    assert not [s for s in sections if s.lower().startswith("related")]
    assert any(row["name"].startswith("Coursework Awards Rule") for row in rows)
    assert all(row["anu_url"].startswith("https://www.anu.edu.au/") for row in rows)
