"""Tiered-fetch logic tests — no network, no Servo engine (both are stubbed)."""

from __future__ import annotations

import pytest
from servo_agent.browser import ServoNotBuilt

import servo_reader.fetch as fetch

RICH_HTML = (
    "<html><head><title>Real Article</title></head><body>"
    "<article><h1>A Real Article</h1>"
    + "<p>" + ("This page has plenty of server-rendered prose. " * 20) + "</p>"
    + "</article></body></html>"
)
SPA_SHELL = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
# Shaped like today's example.com: one short paragraph, well under _MIN_GOOD.
THIN_HTML = (
    "<html><head><title>Example Domain</title></head><body>"
    "<p>This domain is for use in documentation examples.</p></body></html>"
)


def _boom(msg):
    def _raise(*a, **k):
        raise AssertionError(msg)

    return _raise


def _no_engine(*a, **k):
    raise ServoNotBuilt("servoshell binary not found")


def test_good_enough_threshold():
    assert fetch._good_enough("x" * fetch._MIN_GOOD)
    assert not fetch._good_enough("too short")


def test_http_path_wins_for_rich_html(monkeypatch):
    monkeypatch.setattr(
        fetch, "_http_fetch", lambda url, timeout: ("https://x/", "Real Article", RICH_HTML)
    )
    monkeypatch.setattr(fetch, "_servo_fetch", _boom("engine should not run"))
    page = fetch.fetch_markdown("x", engine="auto")
    assert page.meta["source"] == "http"
    assert "server-rendered prose" in page.markdown


def test_auto_falls_back_to_servo_on_thin_content(monkeypatch):
    monkeypatch.setattr(fetch, "_http_fetch", lambda url, timeout: ("https://x/", "App", SPA_SHELL))
    monkeypatch.setattr(
        fetch, "_servo_fetch",
        lambda url, timeout, settle, headless: ("https://x/", "App (rendered)", RICH_HTML),
    )
    page = fetch.fetch_markdown("x", engine="auto")
    assert page.meta["source"] == "servo"
    assert "server-rendered prose" in page.markdown


def test_auto_falls_back_when_http_fails(monkeypatch):
    monkeypatch.setattr(fetch, "_http_fetch", lambda url, timeout: None)
    monkeypatch.setattr(
        fetch, "_servo_fetch",
        lambda url, timeout, settle, headless: ("https://x/", "T", RICH_HTML),
    )
    page = fetch.fetch_markdown("x", engine="auto")
    assert page.meta["source"] == "servo"


def test_force_http_returns_thin_without_engine(monkeypatch):
    monkeypatch.setattr(
        fetch, "_http_fetch", lambda url, timeout: ("https://x/", "App", SPA_SHELL)
    )
    monkeypatch.setattr(fetch, "_servo_fetch", _boom("forced http must not call engine"))
    page = fetch.fetch_markdown("x", engine="http")
    assert page.meta["source"] == "http"


def test_force_http_failure_is_graceful(monkeypatch):
    monkeypatch.setattr(fetch, "_http_fetch", lambda url, timeout: None)
    page = fetch.fetch_markdown("x", engine="http")
    assert page.meta["source"] == "http-failed"
    assert "failed" in page.markdown


def test_auto_keeps_thin_http_page_when_no_engine(monkeypatch):
    monkeypatch.setattr(
        fetch, "_http_fetch", lambda url, timeout: ("https://x/", "Example Domain", THIN_HTML)
    )
    monkeypatch.setattr(fetch, "_servo_fetch", _no_engine)
    page = fetch.fetch_markdown("x", engine="auto")
    assert page.meta["source"] == "http"
    assert page.meta["servo_skipped"] is True
    assert "documentation examples" in page.markdown


def test_rich_http_page_is_not_marked_skipped(monkeypatch):
    monkeypatch.setattr(
        fetch, "_http_fetch", lambda url, timeout: ("https://x/", "Real Article", RICH_HTML)
    )
    monkeypatch.setattr(fetch, "_servo_fetch", _boom("engine should not run"))
    page = fetch.fetch_markdown("x", engine="auto")
    assert "servo_skipped" not in page.meta


def test_forced_servo_without_engine_raises(monkeypatch):
    monkeypatch.setattr(fetch, "_http_fetch", _boom("forced servo must not fetch over http"))
    monkeypatch.setattr(fetch, "_servo_fetch", _no_engine)
    with pytest.raises(ServoNotBuilt):
        fetch.fetch_markdown("x", engine="servo")


def test_auto_without_engine_raises_when_http_also_failed(monkeypatch):
    monkeypatch.setattr(fetch, "_http_fetch", lambda url, timeout: None)
    monkeypatch.setattr(fetch, "_servo_fetch", _no_engine)
    with pytest.raises(ServoNotBuilt):
        fetch.fetch_markdown("x", engine="auto")


def test_scheme_is_added(monkeypatch):
    seen = {}

    def fake_http(url, timeout):
        seen["url"] = url
        return (url, "", RICH_HTML)

    monkeypatch.setattr(fetch, "_http_fetch", fake_http)
    fetch.fetch_markdown("example.com", engine="http")
    assert seen["url"].startswith("https://")
