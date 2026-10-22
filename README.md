# servo-reader (`sr`)

**Read any website in your terminal as clean, rendered markdown — using the real
[Servo](https://servo.org) browser engine.**

Lynx-grade weight, modern-engine fidelity. Unlike `lynx`/`w3m`, JS-rendered sites
work (a real layout + JS engine loads them); unlike a full browser, the output is
calm wrapped markdown in your terminal — no pixels, no Chromium.

**Tiered fetch** keeps it fast: most pages are read over a plain HTTP GET in
**under a second with no engine at all** — Servo is only spun up when a page comes
back thin / JS-gated. So the giant backend is the *fallback*, not the floor.

```
sr --links https://servo.org/about/
sr https://news.ycombinator.com
sr en.wikipedia.org/wiki/Servo_(software)
sr --raw servo.org/about/ | glow -     # pipe raw markdown elsewhere
sr --width 100 --no-pager some.blog/post
```

## How it works

```
URL ─▶ Tier 1: HTTP GET ──── rich content? ──yes──┐
        │                                         │
        └─ thin / JS-gated / failed?              │
            └▶ Tier 2: Servo (headless servoshell + WebDriver)
                        navigate, settle, post-JS DOM ─┤
                                                       ▼
                          servo_agent.distill (trafilatura / markdownify) ─▶ markdown
                            └─ servo_reader.render (zero-dep ANSI + OSC-8 links) ─▶ terminal
```

`--http` forces the cheap path (instant, no engine); `--servo` forces the engine;
default `auto` does Tier 1 → Tier 2. The footer shows which tier won (`via http` /
`via servo`).

It stands on [`servo-agent`](https://github.com/parker-brown-family/servo-agent)
for the engine plumbing and the distiller, and adds a tiny terminal markdown
renderer (no third-party deps — that is the whole point of a *light* reader).

## Install / run

```bash
uv tool install servo-reader
sr --links https://servo.org/about/
```

That puts `sr` on your `PATH`, with `servo-agent` from PyPI. To work from a
clone instead: it is a [uv](https://docs.astral.sh/uv/) project, and a clone
takes `servo-agent` straight from GitHub's `main`, so it builds standalone:

```bash
git clone https://github.com/parker-brown-family/servo-reader
cd servo-reader
uv sync
uv run sr --links https://servo.org/about/
```

> Co-developing against a local `servo-agent` checkout? Override the source in
> `pyproject.toml` with `servo-agent = { path = "../servo-agent", editable = true }`.

### The Servo engine

Pages that come back thin over HTTP are rendered with Servo, which needs
`servoshell`, Servo's browser binary. On Linux, servo-agent (installed with
servo-reader) installs Servo's official build and checks its SHA-256:

```bash
servo-agent install-servo     # the latest Servo release
```

On macOS and Windows, download a build from
[Servo's releases](https://github.com/servo/servo/releases). servo-reader looks
for an engine in this order:

1. `$SERVOSHELL`, the path to a binary
2. `servoshell` on `PATH`
3. the newest engine `servo-agent install-servo` installed
4. a `servo/` directory beside servo-reader's clone, or beside any directory
   above an installed copy, holding an unpacked release (`servo/servoshell`) or a
   source build (`servo/target/release/servoshell` or `servo/target/debug/servoshell`)

```bash
export SERVOSHELL=/path/to/servoshell   # a given binary, or
export SERVO_WEBDRIVER=host:port         # an already-running engine
```

Using `$SERVO_WEBDRIVER` against a warm engine skips the per-call browser launch,
which is faster than starting `servoshell` each time. servo-reader is tested
against Servo 0.7.0 and Servo's nightly build of 2026-10-22.

Most reads never touch the engine. Without one, a page that comes back thin over
HTTP still prints its HTTP text, with a note on stderr that Servo rendering was
skipped, and `--servo` exits with an error. Pass `--http` to stay on the cheap
path always.

## Options

| Flag | Meaning |
|------|---------|
| `-L`, `--links` | append a numbered index of the page's links |
| `-l N`, `--follow N` | follow link `N` from the last page read |
| `-b`, `--back` / `-f`, `--forward` | move through visit history |
| `--history` | list recent pages and exit |
| `--images auto\|kitty\|sixel\|off` | inline images (default `auto`-detect; needs `[images]` extra) |
| `--http` | force the cheap HTTP fetch (instant, no engine) |
| `--servo` | force the Servo engine (renders JS) |
| `--engine auto\|http\|servo` | fetch strategy (default `auto`: HTTP → Servo fallback) |
| `--raw` | emit raw markdown, no ANSI (great for piping) |
| `--no-color` | layout without color |
| `--width N` | wrap width (default: terminal, capped at 100) |
| `--max-chars N` | hard cap on extracted text (default 100k) |
| `--no-settle` | skip the post-load quiet wait (faster, static pages) |
| `--no-pager` | never page through `less` |
| `--timeout S` | navigation timeout |

## Browsing — follow links

Every read remembers the page's links. List them with `--links`, then jump:

```bash
sr --links en.wikipedia.org/wiki/Servo_(software)   # numbered link index
sr -l 4                                              # follow link 4
sr -l 12                                             # …and keep going (the new
                                                     #   page's links are saved too)
```

Reads are also recorded in a **back/forward history** with browser semantics:

```bash
sr --history    # list visited pages (▶ marks where you are)
sr --back       # previous page
sr --forward    # forward again (a new read from a back-position re-branches)
```

State lives in `$XDG_STATE_HOME/servo-reader/` (`last.json` links, `history.json`
stack) — small files, no daemon required for navigation.

## Images (kitty / sixel)

Optionally render a page's figures inline:

```bash
uv sync --extra images    # in a clone; adds Pillow, the only extra dependency
# or, as a uv tool:
uv tool install 'servo-reader[images]'
sr --images auto en.wikipedia.org/wiki/Servo_(software)
```

`auto` detects the terminal's graphics protocol and **stays off when it can't be
sure** — so it never garbles a terminal that can't decode graphics. Supported:
**kitty / WezTerm / Ghostty** (kitty protocol) and **foot / xterm-with-sixel /
Black Box** (sixel). Force one with `--images kitty|sixel`.

Images are fetched only from `http`/`https` hosts with public addresses, so an
image served from `localhost` or a private network shows the placeholder instead
(see [SECURITY.md](SECURITY.md)).

> Note: terminals on the **alacritty backend — including terminal-delight —
> support neither protocol**, so images won't display there (you'll see a
> `🖼 alt-text` placeholder instead). Use a kitty/sixel terminal for the image lane.

## Warm engine (skip the cold start)

Engine-tier reads cold-start a `servoshell` (~2s). Run one persistent engine and
every read attaches to it automatically:

```bash
sr-engine start     # launch a headless servoshell, register its WebDriver port
sr-engine status    # running?  where?  how much memory?
sr ...              # engine reads now attach to the warm one (no env export needed)
sr-engine restart   # a fresh engine, when the warm one has grown
sr-engine stop
```

Servo's memory climbs with every page it opens in one window: Servo 0.7.0 went
from 334 MB to 5.3 GB over 100 pages. A warm engine serves every read, so check
its memory with `status` and `restart` it when it has grown. `stop` asks Servo to
shut down through its own WebDriver route, because Servo 0.7 ignores SIGTERM when
headless, and keeps the engine registered if it is somehow still running.

`sr` discovers the daemon via the same state dir; you can still override with
`$SERVO_WEBDRIVER` to point at any engine. (Measured: an engine read drops from
~2.4s cold to ~1.3s warm.)

## Status

The package version is 0.4.0, which is what `sr --version` prints. Nothing has
been tagged or released, so install from a clone or from the git URL above. It
covers the tiered fetch, link following with back/forward history, the
warm-engine daemon, and inline images. Pillow, for the image lane, is the only
optional dependency.
