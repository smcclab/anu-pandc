"""Read the ANU Policy Library (https://policies.anu.edu.au/ppl).

Four ways in, all server-rendered HTML:

``/ppl/document/ANUP_004603``
    one document.
``/ppl/title/index.htm``
    the A-Z index of every document in the library.
``/ppl/view_all/index.htm?subdoctype_id=Policy``
    every document of one type, and/or under one topic.
``/ppl/search_results/index.htm?searchtype=QUICK&ssUserFullText=...``
    keyword search, which returns only the first five hits per document type
    and says how many there were.

The library is a different system from Programs & Courses: no year in the URL,
because a policy has an effective date rather than a catalogue year, and the
site only ever serves the current version.
"""
from __future__ import annotations

import logging
import re

from anu_pandc.http import fetch_page
from anu_pandc.parse.policy import (BASE_URL, DOC_TYPES, DOCUMENT_NUMBER, FIELDS,
                                    doc_type_of, document_to_markdown, is_document_page,
                                    listing_to_markdown, parse_document, parse_listing,
                                    parse_search)

logger = logging.getLogger(__name__)

DOCUMENT_URL = f"{BASE_URL}/ppl/document"
TITLE_INDEX_URL = f"{BASE_URL}/ppl/title/index.htm"
VIEW_ALL_URL = f"{BASE_URL}/ppl/view_all/index.htm"
SEARCH_URL = f"{BASE_URL}/ppl/search_results/index.htm"


class NotADocument(Exception):
    """The library answers an unknown number with a page that has no document on it."""


def normalise(number: str) -> str:
    """Accept ``4603``, ``anup_004603`` or a full URL; return ``ANUP_004603``."""
    number = number.strip()
    found = DOCUMENT_NUMBER.search(number.upper())
    if found:
        return found.group(0)
    if re.fullmatch(r"\d+", number):
        return f"ANUP_{int(number):06d}"
    raise ValueError(f"{number!r} is not an ANU Policy Library document number")


def url_for(number: str) -> str:
    return f"{DOCUMENT_URL}/{normalise(number)}"


def fetch_document(number: str) -> dict:
    """Fetch and parse one policy-library document."""
    number = normalise(number)
    url = url_for(number)
    logger.info("[fetch] policy %s: %s", number, url)
    soup = fetch_page(url)
    if not is_document_page(soup):
        raise NotADocument(f"{number}: no document at {url}")
    return parse_document(soup, number, url)


def fetch_index() -> list[dict]:
    """Every document in the library, from the A-Z index."""
    logger.info("[fetch] policy index: %s", TITLE_INDEX_URL)
    return parse_listing(fetch_page(TITLE_INDEX_URL))


def fetch_view_all(doc_type: str | None = None, topic: str | None = None,
                   subtopic: str | None = None) -> tuple[list[dict], str]:
    """Every document of a type and/or under a topic. Returns (rows, url)."""
    params = {}
    if doc_type:
        params["subdoctype_id"] = doc_type
    if topic:
        params["ssTopic"] = topic
    if subtopic:
        params["ssSubTopic"] = subtopic
    logger.info("[fetch] policy view_all %s", params or "(everything)")
    response_soup = fetch_page(VIEW_ALL_URL, params=params)
    rows = parse_listing(response_soup)
    if doc_type:
        # view_all labels rows only in some listings; the filter is the answer.
        for row in rows:
            row.setdefault("doc_type", doc_type)
    return rows, _with_params(VIEW_ALL_URL, params)


def search(term: str) -> tuple[list[dict], str]:
    """Keyword search. Returns (rows, url).

    Each row carries ``group`` (the document type) and ``group_total``, because
    the library shows only the first five of each type. When ``group_total``
    exceeds the rows returned, ``fetch_view_all`` gets the rest.
    """
    params = {"searchtype": "QUICK", "ssUserFullText": term}
    logger.info("[fetch] policy search %r", term)
    rows = parse_search(fetch_page(SEARCH_URL, params=params))
    return rows, _with_params(SEARCH_URL, params)


def _with_params(url: str, params: dict) -> str:
    from urllib.parse import urlencode
    return f"{url}?{urlencode(params)}" if params else url


__all__ = ["BASE_URL", "DOC_TYPES", "FIELDS", "NotADocument", "SEARCH_URL",
           "doc_type_of",
           "TITLE_INDEX_URL", "VIEW_ALL_URL", "document_to_markdown", "fetch_document",
           "fetch_index", "fetch_view_all", "listing_to_markdown", "normalise",
           "search", "url_for"]
