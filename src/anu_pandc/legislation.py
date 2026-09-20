"""Read University legislation: ANU's index, and the Federal Register behind it.

ANU legislation — Statutes, Rules and Orders made by Council or the
Vice-Chancellor under s 50 of the *Australian National University Act 1991* —
has the status of federal law and is registered on the Federal Register of
Legislation. So there are two sources, and both are needed:

``https://www.anu.edu.au/about/governance/legislation``
    ANU's own index of the legislation that applies to the University, grouped
    into Acts, Statutes, Rules and Orders. This is the list of what counts; the
    Register has no way to ask "everything ANU made".

``https://api.prod.legislation.gov.au/v1`` (OData) and ``www.legislation.gov.au``
    The Register itself: authoritative status (in force, repealed, ceased),
    commencement and amendment history, what authorises what, and the text.

Text lives in the EPUB the Register publishes, whose inner HTML sits at a URL
built from the title id and the *version start date* — which is why a fetch
asks OData for the versions first.
"""
from __future__ import annotations

import logging
import re

from anu_pandc.http import fetch_json, fetch_page
from anu_pandc.parse.html_md import to_markdown

logger = logging.getLogger(__name__)

ANU_INDEX_URL = "https://www.anu.edu.au/about/governance/legislation"
ANU_BASE_URL = "https://www.anu.edu.au"
API_URL = "https://api.prod.legislation.gov.au/v1"
REGISTER_URL = "https://www.legislation.gov.au"

#: Register ids: C2004A04206 (Act), F2024L01752 (legislative instrument), and
#: the N (notifiable) and G (gazette) series.
TITLE_ID = re.compile(r"\b([CF]\d{4}[ABCGLNW]\d{5})\b")

TITLE_FIELDS = "id,name,collection,subCollection,status,isInForce,isPrincipal,makingDate,asMadeRegisteredAt"

FIELDS = ["id", "name", "kind", "status", "in_force", "made", "url"]


class NoSuchTitle(Exception):
    """Nothing on the Register matches."""


# ---- ANU's index -------------------------------------------------------------


def fetch_anu_index() -> list[dict]:
    """ANU's own list of the legislation that applies to the University.

    Each row is ``{section, name, anu_url}``: the Register id is not on the
    index page, only on the individual pages, so it is resolved on demand.
    """
    logger.info("[fetch] legislation index: %s", ANU_INDEX_URL)
    soup = fetch_page(ANU_INDEX_URL)
    rows: list[dict] = []
    for ul in soup.find_all("ul", class_="linklist"):
        heading = ul.find_previous(["h2", "h3", "h4"])
        section = heading.get_text(" ", strip=True) if heading else ""
        if section.lower().startswith("related"):
            continue
        for a in ul.find_all("a", href=True):
            href = a["href"]
            if "/legislation/" not in href:
                continue
            rows.append({
                "section": section,
                "name": a.get_text(" ", strip=True),
                "anu_url": href if href.startswith("http") else ANU_BASE_URL + href,
            })
    return rows


def resolve_from_anu_page(anu_url: str) -> str:
    """The Register id an ANU legislation page links to, or ''."""
    logger.info("[fetch] legislation page: %s", anu_url)
    found = TITLE_ID.search(str(fetch_page(anu_url)))
    return found.group(1) if found else ""


# ---- the Register ------------------------------------------------------------


def _titles(params: dict) -> list[dict]:
    return fetch_json(f"{API_URL}/titles", params=params).get("value", [])


def search_titles(term: str, in_force_only: bool = False, top: int = 50) -> list[dict]:
    """Titles whose name contains ``term``.

    The Register's own full-text search is not reachable over OData, so this is
    a name match. It is enough to find a named instrument; it will not find a
    phrase buried in the text of one.
    """
    escaped = term.replace("'", "''")
    conditions = [f"contains(name,'{escaped}')"]
    if in_force_only:
        conditions.append("isInForce eq true")
    logger.info("[fetch] legislation search %r", term)
    found = _titles({
        "$filter": " and ".join(conditions),
        "$select": TITLE_FIELDS,
        "$top": top,
    })
    # The Register rejects $orderby, so sort here: newest first.
    found.sort(key=lambda t: t.get("makingDate") or "", reverse=True)
    return found


def fetch_title(title_id: str, versions: bool = False) -> dict:
    """One title's metadata, optionally with its version history."""
    params = {"$filter": f"id eq '{title_id}'", "$expand": "authorisedBy"}
    if versions:
        params["$expand"] = "authorisedBy,versions"
    found = _titles(params)
    if not found:
        raise NoSuchTitle(f"{title_id}: no such title on the Federal Register of Legislation")
    return found[0]


def resolve(query: str, in_force_only: bool = True) -> str:
    """Turn a Register id or an instrument's name into a Register id.

    A name match prefers what is in force and principal, then the most recently
    made, because a name like "Coursework Awards Rule" matches every superseded
    version of itself.
    """
    found = TITLE_ID.search(query.upper())
    if found:
        return found.group(1)
    matches = search_titles(query, in_force_only=in_force_only)
    if not matches and in_force_only:
        matches = search_titles(query, in_force_only=False)
    if not matches:
        raise NoSuchTitle(f"nothing on the Federal Register of Legislation matches {query!r}")
    matches.sort(key=lambda t: (t.get("isInForce", False), t.get("isPrincipal", False),
                                t.get("makingDate") or ""), reverse=True)
    return matches[0]["id"]


def _latest_version(title: dict) -> dict | None:
    versions = title.get("versions") or []
    for version in versions:
        if version.get("isLatest"):
            return version
    return versions[-1] if versions else None


def text_url(title_id: str, version_start: str) -> str:
    """Where the Register serves the document text for a version.

    ``version_start`` is the version's start date (``YYYY-MM-DD``). Without it
    the Register returns its JavaScript shell instead of the document.
    """
    return (f"{REGISTER_URL}/{title_id}/latest/{version_start}"
            "/text/original/epub/OEBPS/document_1/document_1.html")


def fetch_instrument(query: str, in_force_only: bool = True) -> dict:
    """Fetch a title's metadata and its text, by Register id or by name."""
    title_id = resolve(query, in_force_only=in_force_only)
    title = fetch_title(title_id, versions=True)
    data = _tidy(title)
    version = _latest_version(title)
    if version:
        start = str(version.get("start") or "")[:10]
        data["version_start"] = start
        data["compilation"] = version.get("compilationNumber")
        data["registered_at"] = str(version.get("registeredAt") or "")[:10]
        if start:
            url = text_url(title_id, start)
            logger.info("[fetch] legislation text: %s", url)
            data["text_url"] = url
            data["body"] = to_markdown(fetch_page(url), heading_offset=1)
    return data


def summary(title_id: str) -> dict:
    """A title's id, name, kind, status and dates, without fetching its text."""
    return _tidy(fetch_title(title_id))


def _tidy(title: dict) -> dict:
    return {
        "id": title["id"],
        "name": title.get("name", ""),
        "kind": title.get("subCollection") or title.get("collection") or "",
        "status": title.get("status", ""),
        "in_force": bool(title.get("isInForce")),
        "principal": bool(title.get("isPrincipal")),
        "made": str(title.get("makingDate") or "")[:10],
        "registered": str(title.get("asMadeRegisteredAt") or "")[:10],
        "url": f"{REGISTER_URL}/{title['id']}/latest/text",
        "authorised_by": [a.get("affectingTitleId") for a in (title.get("authorisedBy") or [])],
    }


def rows(titles: list[dict]) -> list[dict]:
    return [{k: v for k, v in _tidy(t).items() if k in FIELDS} for t in titles]


# ---- rendering ---------------------------------------------------------------


def instrument_to_markdown(data: dict, scraped_at: str) -> str:
    lines = [f"# {data.get('name', data['id'])}", ""]
    lines.append(f"- **Register id:** {data['id']}")
    lines.append(f"- **URL:** {data.get('url', '')}")
    lines.append(f"- **Scraped:** {scraped_at}")
    if data.get("kind"):
        lines.append(f"- **Kind:** {data['kind']}")
    lines.append(f"- **Status:** {data.get('status', '')}"
                 f"{' (in force)' if data.get('in_force') else ''}")
    if data.get("made"):
        lines.append(f"- **Made:** {data['made']}")
    if data.get("version_start"):
        compilation = data.get("compilation")
        suffix = f", compilation {compilation}" if compilation and compilation != "0" else ""
        lines.append(f"- **Version in force from:** {data['version_start']}{suffix}")
    if data.get("authorised_by"):
        lines.append("- **Authorised by:** " + ", ".join(
            f"[{i}]({REGISTER_URL}/{i}/latest/text)" for i in data["authorised_by"] if i))
    if data.get("text_url"):
        lines.append(f"- **Text:** {data['text_url']}")
    lines.append("")
    if data.get("body"):
        lines += [data["body"], ""]
    return "\n".join(lines).rstrip() + "\n"


def index_to_markdown(rows_: list[dict], scraped_at: str) -> str:
    lines = ["# University legislation", "",
             f"- Source: {ANU_INDEX_URL}",
             f"- Scraped at: {scraped_at}",
             f"- Items: {len(rows_)}", ""]
    section = None
    for row in rows_:
        if row.get("section") != section:
            section = row.get("section")
            lines += ["", f"## {section}", ""]
        register_id = row.get("id", "")
        suffix = f" — {register_id} ({row.get('status', '')})" if register_id else ""
        lines.append(f"- [{row['name']}]({row.get('anu_url', '')}){suffix}")
    return "\n".join(lines).rstrip() + "\n"


def titles_to_markdown(rows_: list[dict], heading: str, scraped_at: str) -> str:
    lines = [f"# {heading}", "",
             f"- Source: {API_URL}/titles",
             f"- Scraped at: {scraped_at}",
             f"- Titles: {len(rows_)}", "",
             "| Id | Name | Kind | Status | Made |",
             "|----|------|------|--------|------|"]
    for row in rows_:
        lines.append(f"| [{row['id']}]({row['url']}) | {row['name']} | {row['kind']} "
                     f"| {row['status']} | {row['made']} |")
    return "\n".join(lines) + "\n"
