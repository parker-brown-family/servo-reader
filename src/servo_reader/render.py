"""Zero-dependency markdown → ANSI renderer for the terminal.

Deliberately small: handles the markdown that :mod:`servo_agent.distill` emits
(headings, emphasis, inline code, links, lists, blockquotes, fenced code, rules)
and lays it out with truecolor ANSI + OSC-8 clickable hyperlinks, word-wrapped to
the terminal width. No third-party deps — that is the whole point of a *light*
reader.
"""

from __future__ import annotations

import re

# ── ANSI ────────────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITAL = "\033[3m"
UNDER = "\033[4m"
STRIKE = "\033[9m"


def _fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


# A calm, readable palette (Solarized-ish).
C_H1 = BOLD + _fg(38, 139, 210)   # blue
C_H2 = BOLD + _fg(42, 161, 152)   # cyan
C_H3 = BOLD + _fg(133, 153, 0)    # green
C_CODE = _fg(203, 75, 22)         # orange
C_LINK = _fg(38, 139, 210)        # blue
C_URL = DIM
C_QUOTE = _fg(147, 161, 161)      # grey
C_BULLET = _fg(181, 137, 0)       # yellow
C_RULE = DIM
C_FENCE = _fg(147, 161, 161)

OSC8 = "\033]8;;{url}\033\\{text}\033]8;;\033\\"

_ANSI_RE = re.compile(r"\033(?:\][^\033]*\033\\|\[[0-9;]*m)")


def _visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


# ── inline parsing ──────────────────────────────────────────────────────────
# Each segment is a styled run of text that carries no internal line breaks.
class Seg:
    __slots__ = ("text", "pre", "post", "url")

    def __init__(self, text: str, pre: str = "", post: str = RESET, url: str | None = None):
        self.text = text
        self.pre = pre
        self.post = post if pre else ""
        self.url = url


_INLINE = re.compile(
    r"(?P<code>`+)(?P<code_body>.+?)(?P=code)"
    r"|!?\[(?P<ltext>[^\]]*)\]\((?P<lurl>(?:\([^()\s]*\)|[^()\s])*)(?:\s+\"[^\"]*\")?\)"
    r"|(?P<b>\*\*|__)(?P<b_body>.+?)(?P=b)"
    r"|(?P<s>~~)(?P<s_body>.+?)(?P=s)"
    r"|(?P<i>[*_])(?P<i_body>.+?)(?P=i)",
    re.DOTALL,
)


def parse_inline(text: str, color: bool = True) -> list[Seg]:
    segs: list[Seg] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            segs.append(Seg(text[pos : m.start()]))
        if m.group("code"):
            segs.append(Seg(m.group("code_body"), C_CODE if color else "", RESET))
        elif m.group("ltext") is not None:
            label = m.group("ltext") or m.group("lurl")
            url = m.group("lurl")
            segs.append(Seg(label, (C_LINK + UNDER) if color else "", RESET, url=url))
        elif m.group("b"):
            segs.append(Seg(m.group("b_body"), BOLD if color else "", RESET))
        elif m.group("s"):
            segs.append(Seg(m.group("s_body"), STRIKE if color else "", RESET))
        elif m.group("i"):
            segs.append(Seg(m.group("i_body"), ITAL if color else "", RESET))
        pos = m.end()
    if pos < len(text):
        segs.append(Seg(text[pos:]))
    return segs


def _emit(seg: Seg, word: str) -> str:
    if seg.url:
        body = f"{seg.pre}{word}{seg.post}" if seg.pre else word
        return OSC8.format(url=seg.url, text=body)
    if seg.pre:
        return f"{seg.pre}{word}{seg.post}"
    return word


def wrap_segments(segs: list[Seg], width: int, indent: str = "", hang: str = "") -> list[str]:
    """Greedy word-wrap a list of styled segments to ``width`` visible columns."""
    lines: list[str] = []
    cur = indent
    col = _visible_len(indent)
    first = True

    def flush():
        nonlocal cur, col, first
        lines.append(cur.rstrip())
        prefix = hang or indent
        cur = prefix
        col = _visible_len(prefix)
        first = False

    for seg in segs:
        # Split on spaces but keep the segment's leading/trailing space behaviour.
        parts = re.split(r"(\s+)", seg.text)
        for part in parts:
            if part == "":
                continue
            if part.isspace():
                if col > _visible_len(indent if first else (hang or indent)):
                    cur += " "
                    col += 1
                continue
            wlen = len(part)
            if col + wlen > width and col > _visible_len(hang or indent):
                flush()
            cur += _emit(seg, part)
            col += wlen
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [indent.rstrip()]


# ── block parsing ───────────────────────────────────────────────────────────
_H = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_UL = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)(.*)$")


def render(md: str, width: int = 80, color: bool = True) -> str:
    width = max(40, width)
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def hr() -> str:
        bar = "─" * min(width, 60)
        return (C_RULE + bar + RESET) if color else bar

    while i < n:
        line = lines[i]

        # fenced code block
        fm = _FENCE.match(line)
        if fm:
            fence = fm.group(1)
            i += 1
            block: list[str] = []
            while i < n and not lines[i].strip().startswith(fence):
                block.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            for bl in block:
                txt = "  " + bl
                out.append((C_FENCE + txt + RESET) if color else txt)
            out.append("")
            continue

        # heading
        hm = _H.match(line)
        if hm:
            level = len(hm.group(1))
            text = hm.group(2).strip()
            segs = parse_inline(text, color)
            plain = "".join(s.text for s in segs)
            if color:
                c = C_H1 if level == 1 else C_H2 if level == 2 else C_H3
                if level == 1:
                    out.append("")
                    out.append(c + plain.upper() + RESET)
                    out.append(C_H1 + "═" * min(_visible_len(plain), width) + RESET)
                else:
                    pref = "#" * level
                    out.append("")
                    out.append(f"{c}{pref} {plain}{RESET}")
            else:
                out.append("")
                out.append(("#" * level) + " " + plain)
            out.append("")
            i += 1
            continue

        # horizontal rule
        if _HR.match(line):
            out.append("")
            out.append(hr())
            out.append("")
            i += 1
            continue

        # blockquote (consume consecutive)
        if _QUOTE.match(line):
            buf: list[str] = []
            while i < n and _QUOTE.match(lines[i]):
                buf.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            segs = parse_inline(" ".join(b for b in buf if b.strip()), color)
            bar = (C_QUOTE + "│ " + RESET) if color else "| "
            for wl in wrap_segments(segs, width - 2):
                out.append(bar + ((C_QUOTE + wl + RESET) if color else wl))
            out.append("")
            continue

        # list item (handle nesting by indent width)
        lm = _UL.match(line) or _OL.match(line)
        if lm:
            while i < n and (_UL.match(lines[i]) or _OL.match(lines[i])):
                ul = _UL.match(lines[i])
                ol = _OL.match(lines[i])
                if ul:
                    lead, body = ul.group(1), ul.group(2)
                    marker = (C_BULLET + "•" + RESET) if color else "*"
                else:
                    lead, num, body = ol.group(1), ol.group(2), ol.group(3)
                    marker = (C_BULLET + f"{num}." + RESET) if color else f"{num}."
                depth = len(lead) // 2
                indent = "  " * depth
                segs = parse_inline(body, color)
                bullet = f"{indent}{marker} "
                hang = indent + "  " + (" " * _visible_len(marker))
                wrapped = wrap_segments(segs, width, indent=bullet, hang=hang)
                out.extend(wrapped)
                i += 1
            out.append("")
            continue

        # blank line
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue

        # paragraph: gather until blank / block start
        para: list[str] = [line]
        i += 1
        while i < n and lines[i].strip() and not (
            _H.match(lines[i]) or _HR.match(lines[i]) or _UL.match(lines[i])
            or _OL.match(lines[i]) or _QUOTE.match(lines[i]) or _FENCE.match(lines[i])
        ):
            para.append(lines[i])
            i += 1
        segs = parse_inline(" ".join(p.strip() for p in para), color)
        out.extend(wrap_segments(segs, width))
        out.append("")

    # collapse trailing blanks
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"
