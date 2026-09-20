"""Fetching pages from the ANU sites this tool reads, politely.

One session, a self-identifying User-Agent, and a small pause before every
request so reading a few hundred pages does not hammer the ANU servers.

Five hosts are involved. Programs & Courses is the original one; the policy
library, MyTimetable, the university calendar and the Federal Register of
Legislation came later. They are listed in ``HOSTS`` so a sandbox that has to
allow-list them can be told all five at once.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from anu_pandc import __version__

BASE_URL = "https://programsandcourses.anu.edu.au"

#: Every host the tool talks to, and what it reads from each.
HOSTS = {
    "programsandcourses.anu.edu.au": "programs, courses and class summaries",
    "policies.anu.edu.au": "the ANU Policy Library",
    "mytimetable.anu.edu.au": "the published class timetable",
    "www.anu.edu.au": "the university calendar and the legislation index",
    "api.prod.legislation.gov.au": "Federal Register of Legislation metadata",
    "www.legislation.gov.au": "Federal Register of Legislation document text",
}

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


def _host_of(url: str) -> str:
    return urlsplit(url).netloc or "the host"


def _forbidden_hint(response: requests.Response) -> str:
    """Explain a 403: the ANU site itself, or something between us and it."""
    host = _host_of(response.url)

    # Agent sandboxes state it outright; nothing left to work out.
    deny_reason = response.headers.get("x-deny-reason")
    if deny_reason:
        return (
            f"403 Forbidden for {response.url}, from your own network's egress "
            f"gateway rather than from ANU (x-deny-reason: {deny_reason}). The host "
            f"{host} is not on this environment's outbound allow-list. No header, "
            "proxy or DNS change gets around a gateway refusal: either have the "
            "host allow-listed, or work offline from a saved tree with --from."
        )

    from_origin = any(h in response.headers for h in _ORIGIN_HEADERS)
    where = (
        f"The response carries {host}'s own headers, so ANU refused it."
        if from_origin
        else f"The response carries none of {host}'s own headers, so it was probably "
        "refused by a proxy, firewall or egress allow-list between you and ANU "
        "rather than by ANU itself."
    )
    served_by = response.headers.get("Server") or response.headers.get("Via")
    served = f" Served by: {served_by}." if served_by else ""
    return (
        f"403 Forbidden for {response.url}. {where}{served}\n"
        f"If you are in a sandbox, allow outbound access to {host}. If ANU is "
        "refusing you, try a slower --rate, or set ANU_PANDC_USER_AGENT to "
        "identify yourself differently."
    )


def _request(method: str, url: str, **kwargs) -> requests.Response:
    if rate_limit_seconds:
        time.sleep(rate_limit_seconds)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    response = session().request(method, url, **kwargs)
    if response.status_code == 403:
        raise Forbidden(_forbidden_hint(response), response=response)
    response.raise_for_status()
    return response


def get(url: str, **kwargs) -> requests.Response:
    """GET with the shared session, rate limit and timeout. Raises on HTTP errors."""
    return _request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    """POST with the same session, rate limit and error handling as ``get``."""
    return _request("POST", url, **kwargs)


def fetch_page(url: str, **kwargs) -> BeautifulSoup:
    """Fetch a URL and return the parsed HTML.

    When the response says nothing about its encoding, the bytes are handed to
    BeautifulSoup so it can read the declaration inside the document. The
    Federal Register serves its document text that way, and ``requests``'
    ISO-8859-1 fallback mangles every dash and every accented name in it.
    """
    response = get(url, **kwargs)
    if "charset=" in response.headers.get("content-type", "").lower():
        return BeautifulSoup(response.text, "html.parser")
    return BeautifulSoup(response.content, "html.parser")


def fetch_json(url: str, **kwargs):
    """Fetch a URL and return the decoded JSON body."""
    return get(url, **kwargs).json()


def absolute(href: str, base: str = BASE_URL) -> str:
    """Make an href from one of the ANU sites absolute."""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{base}{href}"
    return f"{base}/{href}"
