# servo-reader (`sr`)

**Read any website in your terminal as clean, rendered markdown — using the real
[Servo](https://servo.org) browser engine.**

Lynx-grade weight, modern-engine fidelity. Unlike `lynx`/`w3m`, the page is
loaded by an actual layout + JS engine, so client-rendered sites work; unlike a
full browser, the output is calm wrapped markdown in your terminal — no pixels,
no Chromium.

```
sr example.com
sr https://news.ycombinator.com
sr en.wikipedia.org/wiki/Servo_(software)
sr --raw example.com | glow -          # pipe raw markdown elsewhere
sr --width 100 --no-pager some.blog/post
```

## How it works

```
URL ─▶ Servo (headless servoshell + WebDriver)
        └─ navigate, settle, read post-JS DOM (links absolutized)
            └─ servo_agent.distill  (trafilatura / markdownify)  ─▶ markdown
                └─ servo_reader.render  (zero-dep ANSI + OSC-8 links)  ─▶ terminal
```

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

## Options

| Flag | Meaning |
|------|---------|
| `--raw` | emit raw markdown, no ANSI (great for piping) |
| `--no-color` | layout without color |
| `--width N` | wrap width (default: terminal, capped at 100) |
| `--max-chars N` | hard cap on extracted text (default 100k) |
| `--no-settle` | skip the post-load quiet wait (faster, static pages) |
| `--no-pager` | never page through `less` |
| `--timeout S` | navigation timeout |

## Status

v0.1 — basic but real. The debug `servoshell` build makes first paint slow;
setting `$SERVO_WEBDRIVER` against a warm engine is the fix. Roadmap:
link-follow (`sr -l N`) for in-terminal navigation, a persistent engine daemon,
and an optional sixel/kitty image lane.
