"""Fetching pages from Programs & Courses, politely.

One session, a self-identifying User-Agent, and a small pause before every
request so reading a few hundred pages does not hammer the ANU servers.
"""
from __future__ import annotations

import os
import time

import requests
from bs4 import BeautifulSoup

from anu_pandc import __version__

BASE_URL = "https://programsandcourses.anu.edu.au"
DEFAULT_USER_AGENT = f"anu-pandc/{__version__} (+https://github.com/smcclab/anu-pandc)"
USER_AGENT = os.environ.get("ANU_PANDC_USER_AGENT") or DEFAULT_USER_AGENT
DEFAULT_TIMEOUT = 30

# Headers a response from P&C itself carries (Azure App Service). If a 403
# arrives without any of them it more likely came from something in between.
_ORIGIN_HEADERS = ("Request-Context", "ARRAffinity", "Set-Cookie")

# Module-level so the CLI can turn it down for tests or up if asked to.
rate_limit_seconds = 0.5

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT
    return _session


class Forbidden(requests.exceptions.HTTPError):
    """A 403, with a hint about who is likely to have sent it."""


def _forbidden_hint(response: requests.Response) -> str:
    """Explain a 403: P&C itself, or something between us and it."""
    from_origin = any(h in response.headers for h in _ORIGIN_HEADERS)
    where = (
        "The response carries Programs & Courses' own headers, so ANU refused it."
        if from_origin
        else "The response carries none of Programs & Courses' own headers, so it was "
        "probably refused by a proxy, firewall or egress allow-list between you and "
        "ANU rather than by ANU itself."
    )
    served_by = response.headers.get("Server") or response.headers.get("Via")
    served = f" Served by: {served_by}." if served_by else ""
    return (
        f"403 Forbidden for {response.url}. {where}{served}\n"
        "If you are in a sandbox, allow outbound access to "
        "programsandcourses.anu.edu.au. If ANU is refusing you, try a slower "
        "--rate, or set ANU_PANDC_USER_AGENT to identify yourself differently."
    )


def get(url: str, **kwargs) -> requests.Response:
    """GET with the shared session, rate limit and timeout. Raises on HTTP errors."""
    if rate_limit_seconds:
        time.sleep(rate_limit_seconds)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    response = session().get(url, **kwargs)
    if response.status_code == 403:
        raise Forbidden(_forbidden_hint(response), response=response)
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
