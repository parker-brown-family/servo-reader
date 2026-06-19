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

## Status

v0.2 — tiered fetch landed: rich pages read in **~0.5–0.9s over plain HTTP** with
no engine; thin / JS-gated pages fall back to Servo automatically. Measured: HN
front page 0.52s, the Wikipedia "Servo" article 0.89s — both `via http`.

Roadmap: link-follow (`sr -l N`) for in-terminal navigation, a persistent
warm-engine daemon (amortize Servo cold-start to ~0), and an optional sixel/kitty
image lane.
