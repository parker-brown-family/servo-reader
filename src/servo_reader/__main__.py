"""sr — read any website in your terminal as clean markdown, via the Servo engine.

    sr example.com
    sr --links en.wikipedia.org/wiki/Servo_(software)   # show numbered links
    sr -l 3                                             # follow link 3 from the last page
    sr --raw example.com | glow -                       # pipe the raw markdown elsewhere

Tip: `sr-engine start` launches a warm Servo so engine-tier reads skip cold start.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from . import __version__, images, nav
from .fetch import fetch_markdown
from .render import BOLD, C_BULLET, C_LINK, DIM, OSC8, RESET, UNDER, render


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


def _render_link_index(links: list[tuple[str, str]], width: int, color: bool) -> str:
    """A numbered link list for `--links`, with OSC-8 clickable targets."""
    lines = ["", f"{BOLD}Links{RESET}" if color else "Links",
             f"{DIM}{'─' * 5}{RESET}" if color else "─────"]
    n_w = len(str(len(links)))
    text_w = max(20, width - n_w - 4)
    for i, (text, url) in enumerate(links, 1):
        label = text if len(text) <= text_w else text[: text_w - 1] + "…"
        if color:
            link = OSC8.format(url=url, text=f"{C_LINK}{UNDER}{label}{RESET}")
            lines.append(f"{DIM}[{RESET}{C_BULLET}{i:>{n_w}}{RESET}{DIM}]{RESET} {link}")
        else:
            lines.append(f"[{i:>{n_w}}] {label}  {url}")
    return "\n".join(lines) + "\n"


def _make_image_renderer(mode_arg: str, width: int):
    """Build the standalone-image callback, or None if images are off/unsupported."""
    mode = images.detect() if mode_arg == "auto" else (None if mode_arg == "off" else mode_arg)
    if not mode:
        return None
    if not images.available():
        if mode_arg in ("kitty", "sixel"):
            _eprint("\033[2m(images need Pillow: pip install servo-reader[images])\033[0m")
        return None
    return lambda url, alt: images.render_image(url, mode, width)


def _print_history(color: bool) -> int:
    stack, cur = nav.history()
    if not stack:
        print("no history yet")
        return 0
    for i, entry in enumerate(stack):
        mark = "▶" if i == cur else " "
        title = entry.get("title") or entry["url"]
        if color:
            num = f"{C_BULLET}{i:>3}{RESET}"
            print(f"{mark} {num} {title}\n      {DIM}{entry['url']}{RESET}")
        else:
            print(f"{mark} {i:>3} {title}\n      {entry['url']}")
    hint = "\033[2m─── sr --back / --forward to move ───\033[0m" if color else "(--back/--forward)"
    _eprint(hint)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="sr",
        description="Ultra-lightweight terminal web reader (Servo engine → markdown).",
    )
    p.add_argument("url", nargs="?", help="URL to read (scheme optional; https:// assumed)")
    p.add_argument("-l", "--follow", type=int, metavar="N",
                   help="follow link N from the last page read (see --links)")
    p.add_argument("-L", "--links", action="store_true",
                   help="append a numbered index of the page's links")
    p.add_argument("-b", "--back", action="store_true", help="go back to the previous page")
    p.add_argument("-f", "--forward", action="store_true", help="go forward again")
    p.add_argument("--history", action="store_true", help="list recent pages and exit")
    p.add_argument("--images", choices=["auto", "kitty", "sixel", "off"], default="auto",
                   help="inline images: auto-detect terminal (default), force a protocol, or off")
    p.add_argument("--raw", action="store_true", help="emit raw markdown, no ANSI rendering")
    p.add_argument("--no-color", action="store_true", help="render layout but without ANSI color")
    p.add_argument("--width", type=int, default=0, help="wrap width (default: terminal, max 100)")
    p.add_argument("--max-chars", type=int, default=100_000, help="hard cap on extracted text")
    p.add_argument("--no-settle", action="store_true", help="skip post-load quiet wait (faster)")
    p.add_argument("--no-pager", action="store_true", help="never page output through less")
    p.add_argument("--timeout", type=float, default=30.0, help="navigation timeout (s)")
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--engine", choices=["auto", "http", "servo"], default="auto",
        help="fetch strategy (default: auto = cheap HTTP, fall back to Servo if thin)",
    )
    g.add_argument("--http", dest="engine", action="store_const", const="http",
                   help="force the cheap HTTP fetch (no engine, instant)")
    g.add_argument("--servo", dest="engine", action="store_const", const="servo",
                   help="force the Servo engine (renders JS)")
    p.add_argument("--version", action="version", version=f"servo-reader {__version__}")
    args = p.parse_args(argv)

    color = not args.no_color and (sys.stdout.isatty() or os.environ.get("FORCE_COLOR"))

    # --history is a terminal action: list and exit.
    if args.history:
        return _print_history(bool(color))

    # Resolve the navigation target and whether it's a *new* visit (record=True)
    # or a move within existing history (back/forward → don't re-record).
    actions = sum([bool(args.url), args.follow is not None, args.back, args.forward])
    if actions > 1:
        p.error("choose one of: URL, -l/--follow N, -b/--back, -f/--forward")
    record = True
    if args.back:
        target = nav.go_back()
        if not target:
            _eprint("\033[31m✗ no earlier page in history\033[0m")
            return 1
        record = False
    elif args.forward:
        target = nav.go_forward()
        if not target:
            _eprint("\033[31m✗ already at the most recent page\033[0m")
            return 1
        record = False
    elif args.follow is not None:
        target = nav.resolve(args.follow)
        if not target:
            st = nav.load()
            have = len(st.get("links", [])) if st else 0
            why = f" (last page had {have} links)" if have else " (read a page first)"
            _eprint(f"\033[31m✗ no saved link {args.follow}{why}\033[0m")
            return 1
    elif args.url:
        target = args.url
    else:
        p.error("a URL is required (or -l N / --back / --forward / --history)")
    args.url = target

    _note = {
        "auto": "HTTP → Servo fallback",
        "http": "HTTP only",
        "servo": "Servo engine (debug build — first paint is slow)",
    }[args.engine]
    _eprint(f"\033[2m… fetching {args.url} ({_note})\033[0m")
    try:
        page = fetch_markdown(
            args.url,
            max_chars=args.max_chars,
            settle=not args.no_settle,
            timeout=args.timeout,
            engine=args.engine,
        )
    except Exception as e:  # noqa: BLE001 — top-level CLI guard
        _eprint(f"\033[31m✗ {type(e).__name__}: {e}\033[0m")
        return 1

    # Persist links (for `sr -l N`) and record the visit (for `sr --back`).
    links = nav.extract_links(page.markdown)
    nav.save(page.url, links)
    if record:
        nav.push_history(page.url, page.title)

    if args.raw:
        sys.stdout.write(page.markdown if page.markdown.endswith("\n") else page.markdown + "\n")
        return 0

    width = args.width or min(_term_width(), 100)

    header = ""
    if page.title:
        bar = "─" * min(len(page.title), width)
        if color:
            header = f"\033[1m\033[4m{page.title}\033[0m\n\033[2m{page.url}\033[0m\n\n"
        else:
            header = f"{page.title}\n{page.url}\n{bar}\n\n"

    img_cb = _make_image_renderer(args.images, width) if not args.no_color else None
    body = render(page.markdown, width=width, color=bool(color), image_renderer=img_cb)

    index = ""
    if args.links and links:
        index = _render_link_index(links, width, bool(color))

    m = page.meta
    if color:
        hint = f" · {len(links)} links → sr -l N" if links and not args.links else ""
        footer = (
            f"\n\033[2m─── via {m.get('source', '?')} · {m.get('out_chars', 0):,} chars"
            f"{' · truncated' if m.get('truncated') else ''}{hint} ───\033[0m\n"
        )
    else:
        footer = ""
    out = header + body + index + footer

    # Page through less for long output on a tty, like a real reader.
    if not args.no_pager and sys.stdout.isatty() and out.count("\n") > _term_height():
        pager = os.environ.get("PAGER", "less -R")
        try:
            env = {**os.environ, "LESS": "R"}
            proc = subprocess.Popen(pager.split(), stdin=subprocess.PIPE, env=env)
            proc.communicate(out.encode("utf-8", "replace"))
            return proc.returncode or 0
        except Exception:  # noqa: BLE001 — pager optional
            pass
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
