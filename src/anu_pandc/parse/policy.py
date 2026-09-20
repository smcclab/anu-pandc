"""Parse ANU Policy Library pages into structured data and Markdown.

The library (https://policies.anu.edu.au/ppl) holds the University's policies,
procedures, standards, guidelines and forms. Every document has a number of
the form ``ANUP_004603`` and lives at ``/ppl/document/<number>``.

A document page is three things stacked up: the converted document body
(``div#convertedcontent``), an information table (``div#info_block``) carrying
the governance metadata that decides whether the document binds you, and a
related-content box. All three are parsed here.

The listing pages — the A-Z index, the by-type and by-topic lists, and the
search results — are plain tables of links, parsed by ``parse_listing`` and
``parse_search``.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from anu_pandc.parse.html_md import to_markdown

BASE_URL = "https://policies.anu.edu.au"

DOCUMENT_NUMBER = re.compile(r"ANUP_[0-9]+")

# info_block labels, as they appear on the page, mapped to our field names.
_INFO_FIELDS = {
    "title": "title",
    "document type": "doc_type",
    "document number": "number",
    "version": "version",
    "purpose": "purpose",
    "audience": "audience",
    "category": "category",
    "topic/ subtopic": "topic",
    "topic/subtopic": "topic",
    "effective date": "effective_date",
    "next review date": "next_review_date",
    "responsible officer": "responsible_officer",
    "approved by": "approved_by",
    "contact area": "contact_area",
    "authority": "authority",
    "delegations": "delegations",
}
# Fields that are a list of links rather than a single string.
_LINK_FIELDS = {"authority", "delegations"}

#: The document types the library publishes, as ``subdoctype_id`` wants them.
DOC_TYPES = ["Policy", "Procedure", "Standard", "Guideline", "Form"]

#: Search results head each group with the plural ("Policies (5 of 9)"), while
#: the filters want the singular.
GROUP_TO_TYPE = {"policies": "Policy", "procedures": "Procedure",
                 "standards": "Standard", "guidelines": "Guideline", "forms": "Form"}


def doc_type_of(group: str) -> str:
    """The ``subdoctype_id`` for a search-result group heading."""
    return GROUP_TO_TYPE.get(group.strip().lower(), group.strip())

FIELDS = ["number", "title", "doc_type", "topic", "audience", "contact_area", "url"]


def _link(a: Tag) -> dict:
    href = (a.get("href") or "").strip()
    if href.startswith("/"):
        href = BASE_URL + href
    return {"text": a.get_text(" ", strip=True), "url": href}


def _label(text: str) -> str:
    return re.sub(r"[\s ]+", " ", text).strip().rstrip(":").lower()


def _parse_info_block(block: Tag) -> dict:
    """Pull the governance metadata out of the Information table."""
    data: dict = {}
    for a in block.find_all("a", href=True):
        if "pdfdownload" in a["href"]:
            data["pdf_url"] = BASE_URL + a["href"]
            break
    for row in block.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) != 2:
            continue
        field = _INFO_FIELDS.get(_label(cells[0].get_text(" ", strip=True)))
        if not field:
            continue
        if field in _LINK_FIELDS:
            links = [_link(a) for a in cells[1].find_all("a", href=True)]
            value = links or cells[1].get_text(" ", strip=True)
        else:
            value = re.sub(r"\s+", " ", cells[1].get_text(" ", strip=True)).strip()
        if value:
            data[field] = value
    return data


def _parse_related(box: Tag) -> list[dict]:
    """The Related Content box: a document type, then the documents under it."""
    related: list[dict] = []
    for row in box.find("table").find_all("tr", recursive=False):
        cells = row.find_all("td", recursive=False)
        if len(cells) != 2:
            continue
        kind = cells[0].get_text(" ", strip=True)
        for a in cells[1].find_all("a", href=True):
            entry = _link(a)
            entry["kind"] = kind
            entry["number"] = _number_in(entry["url"])
            related.append(entry)
    return related


def _number_in(url: str) -> str:
    found = DOCUMENT_NUMBER.search(url or "")
    return found.group(0) if found else ""


def _fit_body_headings(body: str, data: dict) -> str:
    """Make the body's headings sit under the one the renderer writes.

    A document opens with its own "Policy: Student assessment (coursework)"
    heading, which the page has already said, so that one is dropped and its
    sections are left at level 2. When it is missing or worded differently,
    every heading moves down a level instead, so that nothing competes with the
    page's own title.
    """
    lines = body.split("\n", 1)
    if lines[0].startswith("#"):
        heading = _label(lines[0].lstrip("#"))
        title = _label(data.get("title", ""))
        doc_type = _label(data.get("doc_type", ""))
        if title and heading in (title, f"{doc_type}: {title}"):
            return lines[1].lstrip("\n") if len(lines) > 1 else ""
    return re.sub(r"^(#{1,5})(?= )", r"#\1", body, flags=re.M)


def parse_document(soup: BeautifulSoup, number: str, url: str) -> dict:
    """Parse a ``/ppl/document/<number>`` page."""
    data: dict = {"number": number, "url": url}

    content = soup.find(id="content") or soup
    boxes = content.select("div.box")
    info = soup.find(id="info_block")
    if info:
        data.update(_parse_info_block(info))
    for box in boxes:
        heading = box.find(["h2", "h3"])
        if heading and "related content" in heading.get_text(" ", strip=True).lower():
            data["related"] = _parse_related(box)

    body = soup.find(id="convertedcontent")
    if body:
        data["body"] = _fit_body_headings(to_markdown(body, BASE_URL), data)

    # Fall back to the page title when the info table is missing or renamed.
    if not data.get("title"):
        meta = soup.find("meta", attrs={"name": "contenttitle"})
        if meta and meta.get("content"):
            data["title"] = meta["content"].strip()
    if not data.get("doc_type"):
        meta = soup.find("meta", attrs={"name": "contenttype"})
        if meta and meta.get("content"):
            data["doc_type"] = meta["content"].strip()
    return data


def is_document_page(soup: BeautifulSoup) -> bool:
    """A real document page has either the info table or a converted body."""
    return soup.find(id="info_block") is not None or soup.find(id="convertedcontent") is not None


# ---- listings ----------------------------------------------------------------


def parse_listing(soup: BeautifulSoup) -> list[dict]:
    """Rows from a listing page (A-Z index, by type, by topic).

    Column headings vary between the listings, so they are read from the table
    rather than assumed. Every row has a title linking to a document number.
    """
    content = soup.find(id="content") or soup
    rows: list[dict] = []
    for table in content.find_all("table", class_="full-table"):
        headers = [_label(th.get_text(" ", strip=True))
                   for th in table.find("tr").find_all(["th", "td"])]
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            link = cells[0].find("a", href=True) if cells else None
            if not link or not _number_in(link["href"]):
                continue
            entry = {"number": _number_in(link["href"]),
                     "title": link.get_text(" ", strip=True),
                     "url": BASE_URL + link["href"] if link["href"].startswith("/") else link["href"]}
            for header, cell in zip(headers[1:], cells[1:]):
                field = {"type": "doc_type", "topic/subtopic": "topic",
                         "audience": "audience", "contact area": "contact_area"}.get(header)
                if field:
                    entry[field] = cell.get_text(" ", strip=True)
            rows.append(entry)
    return rows


def parse_search(soup: BeautifulSoup) -> list[dict]:
    """Rows from a quick-search results page.

    The results are grouped under a heading per document type ("Policies (5 of
    9)"), and each group shows only the first five. ``total`` records how many
    that group actually has, so a caller can tell a complete answer from a
    truncated one.
    """
    content = soup.find(id="content") or soup
    rows: list[dict] = []
    group = ""
    total = 0
    for node in content.find_all(["h2", "h3", "div", "table"]):
        if node.name == "div" and "tableheading" in (node.get("class") or []):
            text = node.get_text(" ", strip=True)
            match = re.match(r"(.+?)\s*\((\d+) of (\d+)\)", text)
            if match:
                group, total = match.group(1), int(match.group(3))
            continue
        if node.name in ("h2", "h3"):
            continue
        if node.name != "table":
            continue
        for row in parse_listing_table(node):
            row["group"] = group
            row["group_total"] = total
            rows.append(row)
    return rows


def parse_listing_table(table: Tag) -> list[dict]:
    """Rows of one results table: title link, summary, contact area."""
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        link = cells[0].find("a", href=True) if cells else None
        if not link or not _number_in(link["href"]):
            continue
        rows.append({
            "number": _number_in(link["href"]),
            "title": link.get_text(" ", strip=True),
            "url": BASE_URL + link["href"] if link["href"].startswith("/") else link["href"],
            "summary": cells[1].get_text(" ", strip=True) if len(cells) > 1 else "",
            "contact_area": cells[2].get_text(" ", strip=True) if len(cells) > 2 else "",
        })
    return rows


# ---- rendering ---------------------------------------------------------------


def _render_value(value) -> str:
    if isinstance(value, list):
        return "; ".join(f"[{v['text']}]({v['url']})" if v.get("url") else v["text"] for v in value)
    return str(value)


_HEADER_ORDER = [
    ("doc_type", "Type"),
    ("number", "Number"),
    ("version", "Version"),
    ("effective_date", "Effective"),
    ("next_review_date", "Next review"),
    ("category", "Category"),
    ("topic", "Topic"),
    ("audience", "Audience"),
    ("responsible_officer", "Responsible officer"),
    ("approved_by", "Approved by"),
    ("contact_area", "Contact area"),
    ("authority", "Authority"),
    ("delegations", "Delegations"),
]


def document_to_markdown(data: dict, scraped_at: str) -> str:
    """Render a parsed policy document."""
    doc_type = data.get("doc_type", "Document")
    title = data.get("title", data.get("number", ""))
    lines = [f"# {doc_type}: {title}".strip(), ""]
    lines.append(f"- **URL:** {data.get('url', '')}")
    lines.append(f"- **Scraped:** {scraped_at}")
    for key, label in _HEADER_ORDER:
        if data.get(key):
            lines.append(f"- **{label}:** {_render_value(data[key])}")
    if data.get("pdf_url"):
        lines.append(f"- **PDF:** {data['pdf_url']}")
    lines.append("")

    # The body opens with the document's own Purpose section, so repeating it
    # here would print it twice.
    if data.get("purpose") and not data.get("body"):
        lines += ["## Purpose", "", data["purpose"], ""]
    if data.get("body"):
        lines += [data["body"], ""]
    if data.get("related"):
        lines += ["## Related content", ""]
        for entry in data["related"]:
            kind = f"{entry['kind']}: " if entry.get("kind") else ""
            lines.append(f"- {kind}[{entry['text']}]({entry['url']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def listing_to_markdown(rows: list[dict], heading: str, source: str, scraped_at: str) -> str:
    lines = [f"# {heading}", "",
             f"- Source: {source}",
             f"- Scraped at: {scraped_at}",
             f"- Documents: {len(rows)}", "",
             "| Number | Title | Type | Topic | Contact area |",
             "|--------|-------|------|-------|--------------|"]
    for row in rows:
        lines.append("| {number} | [{title}]({url}) | {doc_type} | {topic} | {contact_area} |".format(
            number=row.get("number", ""),
            title=row.get("title", "").replace("|", "\\|"),
            url=row.get("url", ""),
            doc_type=row.get("doc_type", ""),
            topic=row.get("topic", ""),
            contact_area=row.get("contact_area", ""),
        ))
    return "\n".join(lines) + "\n"
