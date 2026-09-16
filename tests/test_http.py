import pytest
import requests
import responses as resp

from anu_pandc import http


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http, "rate_limit_seconds", 0)


@resp.activate
def test_fetch_page_returns_soup():
    resp.add(resp.GET, "https://example.com", body="<html><body><h1>Test</h1></body></html>")
    assert http.fetch_page("https://example.com").find("h1").get_text() == "Test"


@resp.activate
def test_fetch_page_raises_on_http_error():
    resp.add(resp.GET, "https://example.com", status=404)
    with pytest.raises(requests.exceptions.HTTPError):
        http.fetch_page("https://example.com")


@resp.activate
def test_user_agent_identifies_tool():
    resp.add(resp.GET, "https://example.com", body="<html></html>")
    http.fetch_page("https://example.com")
    assert resp.calls[0].request.headers["User-Agent"].startswith("anu-pandc/")


def test_absolute():
    assert http.absolute("/course/COMP1100/First%20Semester/3695") == \
        "https://programsandcourses.anu.edu.au/course/COMP1100/First%20Semester/3695"
    assert http.absolute("https://x/y") == "https://x/y"
