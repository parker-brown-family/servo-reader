"""Fetch a URL with Servo and distill it to markdown.

Thin glue over :mod:`servo_agent`: launch (or attach to) a headless servoshell,
navigate, grab the post-render DOM with links absolutized, and run it through the
battle-tested :func:`servo_agent.distill.distill` extractor.
"""

from __future__ import annotations

from dataclasses import dataclass

from servo_agent.browser import ServoBrowser
from servo_agent.distill import _distill


@dataclass
class Page:
    url: str
    title: str
    markdown: str
    meta: dict


def fetch_markdown(
    url: str,
    *,
    max_chars: int = 100_000,
    settle: bool = True,
    timeout: float = 30.0,
    headless: bool = True,
) -> Page:
    """Load ``url`` in Servo and return its distilled markdown.

    ``max_chars`` defaults high (a *reader* wants the whole article, unlike the
    agent's token-budget default). Set ``settle=False`` to skip the post-load
    quiet-period wait for snappier reads of static pages.
    """
    if "://" not in url:
        url = "https://" + url
    with ServoBrowser(headless=headless) as br:
        br.navigate(url, timeout=timeout, settle=settle)
        final_url = br.current_url() or url
        title = (br.title() or "").strip()
        html = br.read_html()
    md, meta = _distill(html, url=final_url, max_chars=max_chars)
    return Page(url=final_url, title=title, markdown=md, meta=meta)
