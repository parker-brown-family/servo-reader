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
sr example.com
sr https://news.ycombinator.com
sr en.wikipedia.org/wiki/Servo_(software)
sr --raw example.com | glow -          # pipe raw markdown elsewhere
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

This is a [uv](https://docs.astral.sh/uv/) project. `servo-agent` is pulled
straight from GitHub, so a fresh clone builds standalone:

```bash
git clone https://github.com/parker-brown-family/servo-reader
cd servo-reader
uv sync
uv run sr example.com
```

> Co-developing against a local `servo-agent` checkout? Override the source in
> `pyproject.toml` with `servo-agent = { path = "../servo-agent", editable = true }`.

### The Servo engine

`servo-reader` needs a built `servoshell` binary (Servo's shell). Point it at one
of:

```bash
export SERVOSHELL=/path/to/servo/target/debug/servoshell   # a local build, or
export SERVO_WEBDRIVER=host:port                            # an already-running engine
```

Using `$SERVO_WEBDRIVER` against a warm engine skips the per-call browser launch
and is **much** faster than cold-starting a debug `servoshell` each time. See
[Servo's build docs](https://book.servo.org/hacking/building-servo.html) to
produce the binary.

> Thanks to the tiered fetch, **most reads never touch the engine** — you only
> need a `servoshell` for JS-gated sites (or pass `--http` to stay on the cheap
> path always).

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
pip install 'servo-reader[images]'          # adds Pillow (the only extra dep)
sr --images auto en.wikipedia.org/wiki/Servo_(software)
```

`auto` detects the terminal's graphics protocol and **stays off when it can't be
sure** — so it never garbles a terminal that can't decode graphics. Supported:
**kitty / WezTerm / Ghostty** (kitty protocol) and **foot / xterm-with-sixel /
Black Box** (sixel). Force one with `--images kitty|sixel`.

> Note: terminals on the **alacritty backend — including terminal-delight —
> support neither protocol**, so images won't display there (you'll see a
> `🖼 alt-text` placeholder instead). Use a kitty/sixel terminal for the image lane.

## Warm engine (skip the cold start)

Engine-tier reads cold-start a `servoshell` (~2s). Run one persistent engine and
every read attaches to it automatically:

```bash
sr-engine start     # launch a headless servoshell, register its WebDriver port
sr-engine status    # running?  where?
sr ...              # engine reads now attach to the warm one (no env export needed)
sr-engine stop
```

`sr` discovers the daemon via the same state dir; you can still override with
`$SERVO_WEBDRIVER` to point at any engine. (Measured: an engine read drops from
~2.4s cold to ~1.3s warm.)

## Status

v0.4 — inline images (kitty/sixel, opt-in `[images]` extra) + back/forward
history (`--back`/`--forward`/`--history`). Builds on v0.3 link-following +
warm-engine daemon and v0.2 tiered fetch (rich pages `via http` in ~0.5–0.9s).

The core stays tiny and dependency-free; the image lane is the only optional
dependency (Pillow). That's the feature set rounded out — open an issue for what's
next.
