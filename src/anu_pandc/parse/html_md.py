"""A small HTML-to-Markdown converter for prose pages.

The P&C parsers pull named fields out of a known page shape. The policy
library and the legislation register are the opposite problem: long prose
documents whose structure *is* the content, and whose markup is whatever Word
produced when someone saved the document. So this walks the tree and keeps the
things that carry meaning — headings, paragraphs, lists, tables, links and
emphasis — and drops the rest.

It is deliberately forgiving. Anything it does not recognise contributes its
text, so a markup change loses formatting rather than content.
"""
from __future__ import annotations

import re

from bs4 import NavigableString, Tag
from bs4.element import PreformattedString

_BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
          "table", "tr", "blockquote", "section", "article", "pre"}
_BLOCK_NAMES = sorted(_BLOCK)
_SKIP = {"script", "style", "noscript", "nav", "form", "button", "svg"}
_INLINE_EMPHASIS = {"strong": "**", "b": "**", "em": "_", "i": "_"}


def _clean(text: str) -> str:
    """Tidy a run of text.

    Collapses whitespace, including the non-breaking spaces Word leaves behind,
    and replaces the dot leaders in a legislative table of contents with an
    ellipsis so a contents line stays readable as one line.
    """
    text = re.sub(r"\.{4,}", " \u2026 ", text)
    return re.sub(r"[ \t\u00a0\r\n]+", " ", text).strip()


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|")


def inline(node, base_url: str = "") -> str:
    """Render a node's inline content: text, links and emphasis."""
    if isinstance(node, PreformattedString):
        # Comments (the policy library leaks its templating language into
        # them), doctypes and XML declarations are not content.
        return ""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag) or node.name in _SKIP:
        return ""

    if node.name == "br":
        return "\n"
    if node.name == "a":
        text = _clean("".join(inline(c, base_url) for c in node.children))
        href = (node.get("href") or "").strip()
        if not text:
            return ""
        if not href or href.startswith("#"):
            return text
        if href.startswith("/") and base_url:
            href = base_url + href
        return f"[{text}]({href})"

    inner = "".join(inline(c, base_url) for c in node.children)
    marker = _INLINE_EMPHASIS.get(node.name)
    if marker and _clean(inner):
        return f"{marker}{_clean(inner)}{marker}"
    return inner


# A heading longer than this, or one that ends like a sentence, is prose that
# happens to be marked up as a heading — which is how the Federal Register's
# EPUB renders the subsections of a provision. Rendering those as headings
# turns a rule into a wall of '#####'.
_MAX_HEADING_CHARS = 100
_SENTENCE_END = (".", ";", ":", ",")


def _is_really_a_heading(text: str) -> bool:
    return len(text) <= _MAX_HEADING_CHARS and not text.endswith(_SENTENCE_END)


def _table(node: Tag, base_url: str) -> list[str]:
    rows = []
    for tr in node.find_all("tr"):
        cells = [_escape_cell(_clean(inline(td, base_url)))
                 for td in tr.find_all(["th", "td"], recursive=False)]
        if cells:
            rows.append(cells)
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    # Word tables often have no <th>; use the first row as the header anyway so
    # the result is a valid Markdown table.
    out = ["| " + " | ".join(rows[0]) + " |",
           "|" + "|".join(["---"] * width) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return out


def _roman(n: int) -> str:
    numerals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for value, glyph in numerals:
        while n >= value:
            out += glyph
            n -= value
    return out


def _marker(node: Tag, index: int) -> str:
    """The bullet for item ``index`` (1-based) of ``node``.

    Policy documents number their clauses, cite those numbers, and split a
    single run of clauses across many ``<ol>`` elements — so ``start`` matters
    and is honoured. Lettered and roman sub-lists become bullets that carry
    their own label, because Markdown has no marker for them and the label is
    part of how the clause is cited.
    """
    if node.name != "ol":
        return "-"
    start = node.get("start")
    offset = int(start) - 1 if str(start).isdigit() else 0
    number = offset + index
    kind = (node.get("type") or "1").lower()
    if kind == "a":
        return f"- ({chr(ord('a') + number - 1)})"
    if kind == "i":
        return f"- ({_roman(number)})"
    return f"{number}."


def _list(node: Tag, base_url: str, depth: int) -> list[str]:
    out: list[str] = []
    number = 0
    for li in node.find_all("li", recursive=False):
        number += 1
        bullet = _marker(node, number)
        nested = [c for c in li.find_all(["ul", "ol"], recursive=False)]
        for child in nested:
            child.extract()
        text = _clean(inline(li, base_url))
        indent = "    " * depth
        if text:
            out.append(f"{indent}{bullet} {text}")
        for child in nested:
            out.extend(_list(child, base_url, depth + 1))
    return out


def to_markdown(root: Tag, base_url: str = "", heading_offset: int = 0) -> str:
    """Render a subtree as Markdown.

    ``heading_offset`` pushes the document's own headings down a level or two so
    they sit under a heading the caller has already written.
    """
    blocks: list[str] = []

    def walk(node) -> None:
        if isinstance(node, PreformattedString):
            return
        if isinstance(node, NavigableString):
            text = _clean(str(node))
            if text:
                blocks.append(text)
            return
        if not isinstance(node, Tag) or node.name in _SKIP:
            return

        if re.fullmatch(r"h[1-6]", node.name or ""):
            text = _clean(inline(node, base_url))
            if not text:
                return
            if _is_really_a_heading(text):
                level = min(6, int(node.name[1]) + heading_offset)
                blocks.append("#" * level + " " + text)
            else:
                blocks.append(text)
            return
        if node.name in ("ul", "ol"):
            lines = _list(node, base_url, 0)
            if lines:
                blocks.append("\n".join(lines))
            return
        if node.name == "table":
            lines = _table(node, base_url)
            if lines:
                blocks.append("\n".join(lines))
            return
        if node.name == "hr":
            blocks.append("---")
            return
        if node.name == "blockquote":
            text = _clean(inline(node, base_url))
            if text:
                blocks.append("> " + text)
            return
        # A <p> is a paragraph however it is nested; anything else is only a
        # paragraph when it has no block-level element anywhere beneath it.
        if node.name in ("p", "pre") or node.find(_BLOCK_NAMES) is None:
            text = inline(node, base_url)
            # A <br> inside a paragraph is a real line break; keep it.
            text = "\n".join(_clean(line) for line in text.split("\n"))
            text = re.sub(r"\n{2,}", "\n", text).strip()
            if text:
                blocks.append(text)
            return

        for child in node.children:
            walk(child)

    walk(root)

    # Word emits a lot of empty and duplicate-whitespace blocks.
    out: list[str] = []
    for block in blocks:
        if block and (not out or out[-1] != block):
            out.append(block)
    return "\n\n".join(out).strip()
