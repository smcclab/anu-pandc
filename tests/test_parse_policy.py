from pathlib import Path

from bs4 import BeautifulSoup

from anu_pandc.parse.policy import (doc_type_of, document_to_markdown, is_document_page,
                                    parse_document, parse_listing, parse_search)

FIXTURES = Path(__file__).parent / "fixtures"


def soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / f"{name}.html").read_text(encoding="utf-8"), "html.parser")


def document():
    return parse_document(soup("policy_ANUP_004603"), "ANUP_004603",
                          "https://policies.anu.edu.au/ppl/document/ANUP_004603")


# --- the information table ---

def test_title_and_type():
    data = document()
    assert data["title"] == "Student assessment (coursework)"
    assert data["doc_type"] == "Policy"


def test_governance_metadata():
    data = document()
    assert data["effective_date"] == "25 Nov 2025"
    assert data["next_review_date"] == "25 Nov 2030"
    assert data["approved_by"] == "Academic Board"
    assert data["responsible_officer"] == "Registrar, Student Administration"
    assert data["contact_area"] == "Division of Student Administration and Academic Services"


def test_authority_is_a_list_of_links():
    names = [entry["text"] for entry in document()["authority"]]
    assert "Coursework Awards Rule 2024" in names
    assert all(entry["url"].startswith("http") for entry in document()["authority"])


def test_printable_pdf_is_found():
    assert document()["pdf_url"].startswith("https://policies.anu.edu.au/ppl/pdfdownload/")


def test_related_content_carries_its_kind_and_number():
    related = {entry["number"]: entry for entry in document()["related"]}
    assert related["ANUP_004604"]["kind"] == "Procedures"


# --- the document body ---

def test_body_keeps_the_section_headings():
    body = document()["body"]
    assert "## Purpose" in body
    assert "### Assessment design principles" in body


def test_body_headings_sit_under_the_rendered_title():
    # The document's own title heading is dropped, so its sections are the
    # first level under the "# Policy: ..." the renderer writes.
    body = document()["body"]
    assert not body.startswith("# Policy:")
    assert body.lstrip().startswith("## Purpose")


def test_body_numbers_clauses_as_the_policy_does():
    # The policy cites "Clause 72 of this policy", so the numbering has to
    # survive: it lives in the <ol start=...> attributes, not in the text.
    body = document()["body"]
    assert "\n72. " in body


def test_body_keeps_lettered_subclauses_labelled():
    assert "- (a) align with the strategic directions" in document()["body"]


def test_body_drops_the_template_language_in_the_comments():
    assert "wcmDynamicConversion" not in document()["body"]


def test_body_makes_internal_links_absolute():
    assert "(https://policies.anu.edu.au/ppl/document/ANUP_010007)" in document()["body"]


def test_markdown_leads_with_type_and_title():
    rendered = document_to_markdown(document(), "2026-01-01T00:00:00Z")
    assert rendered.startswith("# Policy: Student assessment (coursework)")
    assert "- **Approved by:** Academic Board" in rendered


def test_is_document_page():
    assert is_document_page(soup("policy_ANUP_004603"))
    assert not is_document_page(BeautifulSoup("<html><body>nope</body></html>", "html.parser"))


# --- listings and search ---

def test_listing_rows_have_numbers_titles_and_columns():
    rows = parse_listing(soup("policy_view_all_Policy"))
    assert rows
    assert all(row["number"].startswith("ANUP_") for row in rows)
    assert all(row["url"].startswith("https://policies.anu.edu.au/") for row in rows)
    assert any(row.get("topic") for row in rows)


def test_search_rows_carry_their_group_and_its_true_size():
    rows = parse_search(soup("policy_search_delegated-authority"))
    policies = [row for row in rows if row["group"] == "Policies"]
    assert len(policies) == 5
    # The library shows five per type and says how many there really are.
    assert policies[0]["group_total"] > 5
    assert policies[0]["title"] == "Delegations of authority"


def test_search_rows_have_summaries():
    rows = parse_search(soup("policy_search_delegated-authority"))
    assert any(row["summary"] for row in rows)


def test_group_headings_map_to_the_filter_value():
    assert doc_type_of("Policies") == "Policy"
    assert doc_type_of("Procedures") == "Procedure"


def test_purpose_is_not_printed_twice():
    rendered = document_to_markdown(document(), "2026-01-01T00:00:00Z")
    assert rendered.count("To describe standards underpinning") == 1
