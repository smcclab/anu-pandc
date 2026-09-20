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


@resp.activate
def test_forbidden_from_origin_names_anu():
    resp.add(
        resp.GET,
        "https://programsandcourses.anu.edu.au/",
        status=403,
        headers={"Request-Context": "appId=cid-v1:x"},
    )
    with pytest.raises(http.Forbidden) as caught:
        http.fetch_page("https://programsandcourses.anu.edu.au/")
    assert "ANU refused it" in str(caught.value)


@resp.activate
def test_forbidden_without_origin_headers_blames_the_middle():
    resp.add(resp.GET, "https://programsandcourses.anu.edu.au/", status=403)
    with pytest.raises(http.Forbidden) as caught:
        http.fetch_page("https://programsandcourses.anu.edu.au/")
    message = str(caught.value)
    assert "egress allow-list" in message
    assert "programsandcourses.anu.edu.au" in message


@resp.activate
def test_forbidden_names_the_host_actually_refused():
    resp.add(resp.GET, "https://policies.anu.edu.au/ppl", status=403)
    with pytest.raises(http.Forbidden) as caught:
        http.fetch_page("https://policies.anu.edu.au/ppl")
    assert "policies.anu.edu.au" in str(caught.value)


@resp.activate
def test_post_uses_the_same_session_and_rate_limit():
    resp.add(resp.POST, "https://mytimetable.anu.edu.au/even/rest/timetable/subjects",
             json={"ok": True})
    assert http.post("https://mytimetable.anu.edu.au/even/rest/timetable/subjects",
                     data={"search-term": "COMP3300"}).json() == {"ok": True}
    assert resp.calls[0].request.headers["User-Agent"].startswith("anu-pandc/")


def test_user_agent_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("ANU_PANDC_USER_AGENT", "my-agent/1.0")
    import importlib

    reloaded = importlib.reload(http)
    try:
        assert reloaded.USER_AGENT == "my-agent/1.0"
    finally:
        monkeypatch.delenv("ANU_PANDC_USER_AGENT")
        importlib.reload(http)


@resp.activate
def test_forbidden_reports_a_gateway_deny_reason_verbatim():
    resp.add(
        resp.GET,
        "https://example.com",
        status=403,
        headers={"x-deny-reason": "host_not_allowed"},
    )
    with pytest.raises(http.Forbidden) as caught:
        http.fetch_page("https://example.com")
    message = str(caught.value)
    assert "host_not_allowed" in message
    assert "egress gateway" in message
