from bs4 import BeautifulSoup

from anu_pandc.parse.html_md import to_markdown


def md(html: str, **kwargs) -> str:
    return to_markdown(BeautifulSoup(html, "html.parser"), **kwargs)


def test_headings_and_paragraphs():
    assert md("<h2>Scope</h2><p>Applies to all staff.</p>") == "## Scope\n\nApplies to all staff."


def test_heading_offset_pushes_headings_under_the_callers_own():
    assert md("<h1>Policy</h1>", heading_offset=1).startswith("## ")


def test_ordered_lists_honour_start_because_clauses_are_cited_by_number():
    out = md('<ol start="13"><li>The hurdle is approved.</li><li>And published.</li></ol>')
    assert out == "13. The hurdle is approved.\n14. And published."


def test_lettered_sublists_keep_their_label():
    out = md('<ol type="a"><li>first</li><li>second</li></ol>')
    assert out == "- (a) first\n- (b) second"


def test_roman_sublists_keep_their_label():
    assert md('<ol type="i" start="4"><li>fourth</li></ol>') == "- (iv) fourth"


def test_nested_lists_are_indented():
    out = md("<ul><li>outer<ul><li>inner</li></ul></li></ul>")
    assert out == "- outer\n    - inner"


def test_links_are_kept_and_made_absolute():
    out = md('<p>See <a href="/ppl/document/ANUP_1">the policy</a>.</p>',
             base_url="https://policies.anu.edu.au")
    assert out == "See [the policy](https://policies.anu.edu.au/ppl/document/ANUP_1)."


def test_an_in_page_anchor_becomes_plain_text():
    # A link to a bookmark inside the same page is meaningless once the page is
    # a Markdown file, but its text is part of the sentence.
    assert md('<p>See <a href="#top">above</a>.</p>') == "See above."


def test_emphasis_survives():
    assert md("<p>This is <strong>required</strong>.</p>") == "This is **required**."


def test_tables_become_markdown_tables():
    out = md("<table><tr><th>Task</th><th>Weight</th></tr>"
             "<tr><td>Exam</td><td>50%</td></tr></table>")
    assert out.splitlines() == ["| Task | Weight |", "|---|---|", "| Exam | 50% |"]


def test_a_pipe_in_a_cell_is_escaped():
    assert "a \\| b" in md("<table><tr><td>a | b</td></tr></table>")


def test_comments_and_doctypes_are_not_content():
    assert md("<!DOCTYPE html><!--idoc leakage--><p>Real text.</p>") == "Real text."


def test_scripts_and_styles_are_dropped():
    assert md("<style>p{color:red}</style><script>x=1</script><p>Text.</p>") == "Text."


def test_non_breaking_spaces_are_collapsed():
    assert md("<p>a  b</p>") == "a b"


def test_dot_leaders_in_a_contents_line_become_an_ellipsis():
    assert md("<p>Part 1 — Preliminary...........1</p>") == "Part 1 — Preliminary … 1"


def test_deeply_wrapped_paragraphs_do_not_run_together():
    # A document whose paragraphs sit several containers deep must still come
    # out as separate blocks.
    out = md("<html><body><div><div><p>One.</p><p>Two.</p></div></div></body></html>")
    assert out == "One.\n\nTwo."


def test_a_br_inside_a_paragraph_is_a_line_break():
    assert md("<p>one<br/>two</p>") == "one\ntwo"


def test_a_sentence_marked_up_as_a_heading_is_rendered_as_prose():
    # The Federal Register's EPUB marks the subsections of a provision as <h5>
    # and <h6>. Left as headings they bury the real structure.
    long_sentence = ("The Associate Dean of an ANU College may, in writing, appoint a "
                     "member of the staff of the college to be a Delegated Authority.")
    assert md(f"<h5>{long_sentence}</h5>") == long_sentence


def test_a_real_heading_is_still_a_heading():
    assert md("<h4>59 Appointment of Delegated Authorities</h4>") == \
        "#### 59 Appointment of Delegated Authorities"
