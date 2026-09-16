"""Fetching pages from Programs & Courses, politely.

One session, a fixed User-Agent, and a small pause before every request so a
bulk scrape of a few hundred pages does not hammer the ANU servers.
"""
from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

from anu_pandc import __version__

BASE_URL = "https://programsandcourses.anu.edu.au"
USER_AGENT = f"anu-pandc/{__version__} (+https://gitlab.anu.edu.au/u4110680/anu-pandc)"
DEFAULT_TIMEOUT = 30

# Module-level so the CLI can turn it down for tests or up if asked to.
rate_limit_seconds = 0.5

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT
    return _session


def get(url: str, **kwargs) -> requests.Response:
    """GET with the shared session, rate limit and timeout. Raises on HTTP errors."""
    if rate_limit_seconds:
        time.sleep(rate_limit_seconds)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    response = session().get(url, **kwargs)
    response.raise_for_status()
    return response


def fetch_page(url: str) -> BeautifulSoup:
    """Fetch a URL and return the parsed HTML."""
    return BeautifulSoup(get(url).text, "html.parser")


def absolute(href: str) -> str:
    """Make a Programs & Courses href absolute."""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    return f"{BASE_URL}/{href}"
