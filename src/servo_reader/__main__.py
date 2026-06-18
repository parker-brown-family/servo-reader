"""sr — read any website in your terminal as clean markdown, via the Servo engine.

    sr example.com
    sr https://news.ycombinator.com
    sr --raw example.com | glow -      # pipe the raw markdown elsewhere
    sr --width 100 en.wikipedia.org/wiki/Servo_(software)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from . import __version__
from .fetch import fetch_markdown
from .render import render


def _term_width(default: int = 80) -> int:
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def _term_height(default: int = 24) -> int:
    try:
        return shutil.get_terminal_size((80, default)).lines
    except Exception:
        return default


def _eprint(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="sr",
        description="Ultra-lightweight terminal web reader (Servo engine → markdown).",
    )
    p.add_argument("url", help="URL to read (scheme optional; https:// assumed)")
    p.add_argument("--raw", action="store_true", help="emit raw markdown, no ANSI rendering")
    p.add_argument("--no-color", action="store_true", help="render layout but without ANSI color")
    p.add_argument("--width", type=int, default=0, help="wrap width (default: terminal, max 100)")
    p.add_argument("--max-chars", type=int, default=100_000, help="hard cap on extracted text")
    p.add_argument("--no-settle", action="store_true", help="skip post-load quiet wait (faster)")
    p.add_argument("--no-pager", action="store_true", help="never page output through less")
    p.add_argument("--timeout", type=float, default=30.0, help="navigation timeout (s)")
    p.add_argument("--version", action="version", version=f"servo-reader {__version__}")
    args = p.parse_args(argv)

    _eprint(f"\033[2m… fetching {args.url} via Servo (debug build — first paint is slow)\033[0m")
    try:
        page = fetch_markdown(
            args.url,
            max_chars=args.max_chars,
            settle=not args.no_settle,
            timeout=args.timeout,
        )
    except Exception as e:  # noqa: BLE001 — top-level CLI guard
        _eprint(f"\033[31m✗ {type(e).__name__}: {e}\033[0m")
        return 1

    if args.raw:
        sys.stdout.write(page.markdown if page.markdown.endswith("\n") else page.markdown + "\n")
        return 0

    width = args.width or min(_term_width(), 100)
    color = not args.no_color and (sys.stdout.isatty() or os.environ.get("FORCE_COLOR"))

    header = ""
    if page.title:
        bar = "─" * min(len(page.title), width)
        if color:
            header = f"\033[1m\033[4m{page.title}\033[0m\n\033[2m{page.url}\033[0m\n\n"
        else:
            header = f"{page.title}\n{page.url}\n{bar}\n\n"

    body = render(page.markdown, width=width, color=bool(color))
    footer = ""
    m = page.meta
    if color:
        footer = (
            f"\n\033[2m─── {m.get('extractor', '?')} · "
            f"{m.get('out_chars', 0):,} chars"
            f"{' · truncated' if m.get('truncated') else ''} ───\033[0m\n"
        )
    out = header + body + footer

    # Page through less for long output on a tty, like a real reader.
    if not args.no_pager and sys.stdout.isatty() and out.count("\n") > _term_height():
        pager = os.environ.get("PAGER", "less -R")
        try:
            proc = subprocess.Popen(pager.split(), stdin=subprocess.PIPE, env={**os.environ, "LESS": "R"})
            proc.communicate(out.encode("utf-8", "replace"))
            return proc.returncode or 0
        except Exception:  # noqa: BLE001 — pager optional
            pass
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
