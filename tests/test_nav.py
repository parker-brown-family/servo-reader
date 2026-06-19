"""Link-extraction, state persistence, and daemon discovery — no network/engine."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def state(tmp_path, monkeypatch):
    """Point XDG_STATE_HOME at a tmp dir and give fresh module instances."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    import servo_reader.daemon as daemon
    import servo_reader.nav as nav

    importlib.reload(nav)
    importlib.reload(daemon)
    return nav, daemon


def test_extract_links_orders_and_dedupes():
    from servo_reader.nav import extract_links

    md = (
        "See [A](https://a.example) and [B](https://b.example).\n"
        "Again [A second time](https://a.example) and an image ![x](https://img.example/p.png).\n"
    )
    links = extract_links(md)
    assert [u for _, u in links] == ["https://a.example", "https://b.example"]
    assert links[0][0] == "A"  # first text wins, image excluded


def test_extract_links_keeps_balanced_parens_in_url():
    from servo_reader.nav import extract_links

    md = "[concurrency](https://en.wikipedia.org/wiki/Concurrency_(computer_science))"
    links = extract_links(md)
    assert links == [("concurrency", "https://en.wikipedia.org/wiki/Concurrency_(computer_science)")]


def test_save_load_resolve_roundtrip(state):
    nav, _ = state
    nav.save("https://page", [("First", "https://1"), ("Second", "https://2")])
    st = nav.load()
    assert st["url"] == "https://page"
    assert nav.resolve(1) == "https://1"
    assert nav.resolve(2) == "https://2"
    assert nav.resolve(99) is None


def test_resolve_without_state_is_none(state):
    nav, _ = state
    assert nav.resolve(1) is None
    assert nav.load() is None


def test_history_push_back_forward(state):
    nav, _ = state
    nav.push_history("https://a", "A")
    nav.push_history("https://b", "B")
    nav.push_history("https://c", "C")
    stack, cur = nav.history()
    assert [e["url"] for e in stack] == ["https://a", "https://b", "https://c"]
    assert cur == 2
    assert nav.go_back() == "https://b"
    assert nav.go_back() == "https://a"
    assert nav.go_back() is None  # at the start
    assert nav.go_forward() == "https://b"


def test_history_new_visit_truncates_forward(state):
    nav, _ = state
    for u in ("https://a", "https://b", "https://c"):
        nav.push_history(u)
    nav.go_back()  # cursor at b
    nav.push_history("https://d")  # new branch from b
    stack, cur = nav.history()
    assert [e["url"] for e in stack] == ["https://a", "https://b", "https://d"]
    assert cur == 2
    assert nav.go_forward() is None  # nothing ahead of the new branch


def test_history_dedupes_consecutive(state):
    nav, _ = state
    nav.push_history("https://a", "A")
    nav.push_history("https://a", "A2")
    stack, _ = nav.history()
    assert len(stack) == 1 and stack[0]["title"] == "A2"


def test_daemon_endpoint_none_when_not_running(state):
    _, daemon = state
    assert daemon.endpoint() is None
    assert daemon.status() == 1


def test_daemon_alive_checks_pid_and_port(state, monkeypatch):
    _, daemon = state
    # Register a fake engine whose pid is alive but port is closed → not alive.
    daemon._engine_file().write_text('{"pid": 1, "host": "127.0.0.1", "port": 1}')
    monkeypatch.setattr(daemon.os, "kill", lambda *a: None)  # pretend pid 1 exists
    monkeypatch.setattr(daemon, "_port_open", lambda h, p, timeout=1.0: False)
    assert daemon.endpoint() is None
    monkeypatch.setattr(daemon, "_port_open", lambda h, p, timeout=1.0: True)
    assert daemon.endpoint() == "127.0.0.1:1"
