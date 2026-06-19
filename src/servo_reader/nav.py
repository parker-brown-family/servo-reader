"""Link extraction + tiny cross-invocation state, so `sr -l N` can follow links.

Each read persists the page's links (numbered, deduped) to a small JSON file under
`$XDG_STATE_HOME/servo-reader/`. A later `sr -l N` resolves link N from that file
and reads it — turning the one-shot viewer into something you can actually browse.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Markdown links to absolute http(s) targets (images excluded via the `!` guard).
# The URL body allows one level of balanced parens so targets like
# `…/Concurrency_(computer_science)` aren't truncated at the first ')'.
_LINK_RE = re.compile(r"(?<!\!)\[([^\]]*)\]\((https?://(?:\([^()\s]*\)|[^()\s])*)\)")


def extract_links(md: str) -> list[tuple[str, str]]:
    """Ordered, deduped ``(text, url)`` for every http(s) link in the markdown."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for m in _LINK_RE.finditer(md):
        text = re.sub(r"\s+", " ", m.group(1)).strip()
        url = m.group(2).rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        out.append((text or url, url))
    return out


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    p = Path(base) / "servo-reader"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _last_file() -> Path:
    return _state_dir() / "last.json"


def save(url: str, links: list[tuple[str, str]]) -> None:
    payload = {
        "url": url,
        "links": [{"n": i + 1, "text": t, "url": u} for i, (t, u) in enumerate(links)],
    }
    _last_file().write_text(json.dumps(payload))


def load() -> dict | None:
    f = _last_file()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return None


def resolve(n: int) -> str | None:
    """URL of link ``n`` from the last read page, or ``None``."""
    st = load()
    if not st:
        return None
    for link in st.get("links", []):
        if link.get("n") == n:
            return link.get("url")
    return None
