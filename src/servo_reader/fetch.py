"""Fetch a URL and distill it to markdown — cheap path first, engine as fallback.

Tiered strategy (the whole point of a *light* reader):

  1. **HTTP** — a plain `requests.get`, distilled. Instant, needs no engine. Wins
     for the ~80% of pages that ship real HTML.
  2. **Servo** — only when the cheap path comes back thin / JS-gated (an SPA shell
     with no server-rendered content) or fails. This is where the real browser
     engine earns its 1.9GB: it executes JS and returns the rendered DOM.

`engine="auto"` (default) does 1→2. `engine="http"` / `engine="servo"` force a tier.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

from servo_agent.distill import distill

_TRUNC_MARKER = "[truncated at "
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) servo-reader/0.2 "
    "(+https://github.com/parker-brown-family/servo-reader)"
)
# Distilled chars below which the cheap HTTP path is deemed "thin" and we escalate
# to the engine (an SPA shell typically distills to ~nothing).
_MIN_GOOD = 300
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


@dataclass
class Page:
    url: str
    title: str
    markdown: str
    meta: dict


def _meta(md: str, source: str) -> dict:
    return {
        "out_chars": len(md),
        "source": source,
        "truncated": md.rstrip().endswith("chars]") and _TRUNC_MARKER in md,
    }


def _good_enough(md: str) -> bool:
    """Did the cheap path return real, readable content (vs an empty SPA shell)?"""
    return len(md.strip()) >= _MIN_GOOD


def _http_fetch(url: str, timeout: float) -> tuple[str, str, str] | None:
    """Cheap path: plain GET. Returns ``(final_url, title, html)`` or ``None``.

    ``None`` means "fall back to the engine" — request failed, non-200, or the
    response wasn't HTML.
    """
    try:
        r = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml,*/*"},
        )
    except requests.RequestException:
        return None
    ctype = r.headers.get("content-type", "").lower()
    if r.status_code != 200:
        return None
    if ctype and "html" not in ctype and "xml" not in ctype:
        return None  # PDFs, JSON, images, … aren't ours to distill
    m = _TITLE_RE.search(r.text)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return (str(r.url), title, r.text)


def _servo_fetch(
    url: str, timeout: float, settle: bool, headless: bool
) -> tuple[str, str, str]:
    """Engine path: render with a real Servo and read the post-JS DOM.

    Auto-attaches to a warm `sr-engine` daemon if one is running (and the caller
    hasn't already pinned `$SERVO_WEBDRIVER`), avoiding a per-call cold start.
    """
    from servo_agent.browser import ServoBrowser

    if not os.environ.get("SERVO_WEBDRIVER"):
        try:
            from . import daemon

            ep = daemon.endpoint()
            if ep:
                os.environ["SERVO_WEBDRIVER"] = ep
        except Exception:  # noqa: BLE001 — daemon discovery is best-effort
            pass

    with ServoBrowser(headless=headless) as br:
        br.navigate(url, timeout=timeout, settle=settle)
        final_url = br.current_url() or url
        title = (br.title() or "").strip()
        html = br.read_html()
    return final_url, title, html


def fetch_markdown(
    url: str,
    *,
    max_chars: int = 100_000,
    settle: bool = True,
    timeout: float = 30.0,
    headless: bool = True,
    engine: str = "auto",
) -> Page:
    """Load ``url`` and return its distilled markdown.

    ``engine``: ``"auto"`` (HTTP, fall back to Servo), ``"http"`` (cheap only),
    or ``"servo"`` (force the engine). ``max_chars`` defaults high — a *reader*
    wants the whole article.
    """
    if "://" not in url:
        url = "https://" + url

    # Tier 1 — cheap HTTP (for auto + http).
    if engine in ("auto", "http"):
        got = _http_fetch(url, timeout=min(timeout, 15.0))
        if got:
            final_url, title, html = got
            md = distill(html, url=final_url, max_chars=max_chars)
            if engine == "http" or _good_enough(md):
                return Page(final_url, title, md, _meta(md, "http"))
        elif engine == "http":
            return Page(url, "", "(no content: HTTP fetch failed)", _meta("", "http-failed"))

    # Tier 2 — Servo engine (auto-fallback or forced).
    final_url, title, html = _servo_fetch(url, timeout=timeout, settle=settle, headless=headless)
    md = distill(html, url=final_url, max_chars=max_chars)
    return Page(final_url, title, md, _meta(md, "servo"))
