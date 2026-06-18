"""Renderer unit tests — no Servo engine required (pure markdown → ANSI)."""

from __future__ import annotations

import re

from servo_reader.render import parse_inline, render, wrap_segments

ANSI = re.compile(r"\033(?:\][^\033]*\033\\|\[[0-9;]*m)")


def strip(s: str) -> str:
    return ANSI.sub("", s)


def test_plain_text_roundtrips():
    out = render("# Hello\n\nWorld text here.\n", color=False)
    flat = strip(out)
    assert "Hello" in flat
    assert "World text here." in flat


def test_heading_h1_uppercased_in_color():
    out = render("# title\n", color=True)
    assert "TITLE" in strip(out)
    assert "═" in out  # H1 underline rule


def test_inline_link_becomes_osc8_hyperlink():
    out = render("A [label](https://servo.org) here.\n", color=True)
    assert "\033]8;;https://servo.org\033\\" in out
    assert "label" in strip(out)


def test_bullet_list_renders_marker():
    out = render("- one\n- two\n", color=False)
    flat = strip(out)
    assert "one" in flat and "two" in flat
    assert "*" in flat  # ascii bullet in no-color mode


def test_wrap_respects_width():
    segs = parse_inline("word " * 40, color=False)
    lines = wrap_segments(segs, width=30)
    assert all(len(strip(line)) <= 30 for line in lines)


def test_code_fence_passthrough():
    md = "```\nx = 1\ny = 2\n```\n"
    flat = strip(render(md, color=False))
    assert "x = 1" in flat and "y = 2" in flat


def test_no_ansi_when_color_false():
    out = render("**bold** and *italic* and `code`\n", color=False)
    assert "\033" not in out
