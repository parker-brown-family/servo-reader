"""Image-lane tests: env detection (no deps) + encoders (Pillow-gated)."""

from __future__ import annotations

import pytest

from servo_reader import images


def test_detect_kitty_from_env(monkeypatch):
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    assert images.detect() == "kitty"


def test_detect_sixel_from_term(monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("GHOSTTY_RESOURCES_DIR", raising=False)
    monkeypatch.setenv("TERM", "foot")
    assert images.detect() == "sixel"


def test_detect_none_for_plain_terminal(monkeypatch):
    # alacritty-class terminals (incl. terminal-delight) → no graphics
    for var in ("KITTY_WINDOW_ID", "TERM_PROGRAM", "GHOSTTY_RESOURCES_DIR", "SERVO_READER_SIXEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert images.detect() is None


def test_render_image_none_without_pillow(monkeypatch):
    monkeypatch.setattr(images, "available", lambda: False)
    assert images.render_image("https://x/i.png", "kitty", 80) is None


# ── encoder tests (need Pillow) ───────────────────────────────────────────────
PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _img(w=4, h=4):
    return Image.new("RGB", (w, h), (200, 30, 30))


def test_to_kitty_escape_shape():
    out = images.to_kitty(_img(2, 2))
    assert out.startswith("\033_G")
    assert "f=32" in out and "s=2,v=2" in out
    assert out.rstrip("\n").endswith("\033\\")


def test_to_sixel_escape_shape():
    out = images.to_sixel(_img(4, 4))
    assert out.startswith("\033Pq")
    assert "#0;2;" in out  # at least one color register
    assert out.rstrip("\n").endswith("\033\\")
