"""CLI behaviour when no Servo engine is installed — network and engine are stubbed."""

from __future__ import annotations

import pytest
from servo_agent.browser import ServoNotBuilt

import servo_reader.fetch as fetch
from servo_reader.__main__ import main

THIN_HTML = (
    "<html><head><title>Example Domain</title></head><body>"
    "<p>This domain is for use in documentation examples.</p></body></html>"
)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    # main() saves links and history; keep them out of the real state dir.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


def _no_engine(*a, **k):
    raise ServoNotBuilt("servoshell binary not found")


def test_thin_page_without_engine_prints_http_text_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        fetch,
        "_http_fetch",
        lambda url, timeout: ("https://example.com/", "Example Domain", THIN_HTML),
    )
    monkeypatch.setattr(fetch, "_servo_fetch", _no_engine)

    assert main(["--no-pager", "--no-color", "--links", "https://example.com"]) == 0

    out, err = capsys.readouterr()
    assert "documentation examples" in out
    assert "Servo rendering skipped" in err
    assert "$SERVOSHELL" in err


def test_forced_servo_without_engine_is_an_error(monkeypatch, capsys):
    monkeypatch.setattr(fetch, "_servo_fetch", _no_engine)

    assert main(["--no-pager", "--no-color", "--servo", "https://example.com"]) == 1

    out, err = capsys.readouterr()
    assert out == ""
    assert "no servoshell found" in err
    assert "$SERVOSHELL" in err
