"""Optional inline-image lane: render page figures via the kitty graphics
protocol or sixel.

Kept out of the core path — needs Pillow (the `[images]` extra, e.g.
`uv sync --extra images`) to decode arbitrary web image formats. Terminal support
varies: kitty / WezTerm / Ghostty speak the kitty protocol; foot /
xterm-with-sixel / Black Box speak sixel.
Terminals on the alacritty backend (incl. terminal-delight) support neither, so
:func:`detect` stays conservative and returns ``None`` for them — we never emit
graphics escapes to a terminal that would garble on them.
"""

from __future__ import annotations

import base64
import io
import ipaddress
import os
import socket
from urllib.parse import urljoin, urlsplit

_MAX_BYTES = 8 * 1024 * 1024  # skip absurdly large images
_MAX_REDIRECTS = 3            # each hop is re-checked before it is requested
_REDIRECT_CODES = (301, 302, 303, 307, 308)
_CELL_PX = (8, 16)            # rough char-cell size for column→pixel sizing
_MAX_PX_H = 480               # cap height so sixel encoding stays snappy


def detect() -> str | None:
    """Best-effort graphics protocol from the environment, or ``None``.

    Conservative by design: only returns a protocol when we're fairly sure, so
    `--images auto` is safe to leave on everywhere.
    """
    env = os.environ
    if env.get("KITTY_WINDOW_ID") or env.get("TERM") == "xterm-kitty":
        return "kitty"
    if env.get("TERM_PROGRAM") in ("WezTerm", "ghostty") or env.get("GHOSTTY_RESOURCES_DIR"):
        return "kitty"
    term = env.get("TERM", "")
    if "kitty" in term:
        return "kitty"
    if "foot" in term or "sixel" in term or env.get("SERVO_READER_SIXEL"):
        return "sixel"
    return None


def available() -> bool:
    """True when Pillow is installed (the image lane's only extra dependency)."""
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


def _is_public_ip(addr: str) -> bool:
    """True only for a globally routable unicast address."""
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])  # drop an IPv6 zone id
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is still loopback
    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
        or not ip.is_global
    )


def _public_destination(url: str) -> bool:
    """May an image be requested from ``url``?

    A page chooses its own image URLs, so without this a hostile page could make
    the reader send requests to loopback services, the local network, or a cloud
    metadata endpoint such as 169.254.169.254. Only http(s) is allowed, and every
    address the host resolves to must be public. The connection resolves the name
    again, so a DNS server that answers differently the second time is not
    covered; the check targets URLs that point inward directly or by name.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (ValueError, OSError, UnicodeError):  # bad port, unresolvable, bad IDNA
        return False
    return bool(infos) and all(_is_public_ip(info[4][0]) for info in infos)


def _read_capped(r) -> bytes | None:
    """The response body, or ``None`` when it is empty or larger than _MAX_BYTES."""
    data = bytearray()
    for chunk in r.iter_content(64 * 1024):
        data += chunk
        if len(data) > _MAX_BYTES:
            return None
    return bytes(data) or None


def _fetch(url: str, timeout: float = 15.0) -> bytes | None:
    """GET an image from a public address, following at most _MAX_REDIRECTS hops.

    Redirects are followed here rather than by requests, so that every new
    destination passes :func:`_public_destination` before it is requested.
    """
    import requests

    for _ in range(_MAX_REDIRECTS + 1):
        if not _public_destination(url):
            return None
        try:
            r = requests.get(
                url,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
                headers={"User-Agent": "servo-reader/0.4"},
            )
            with r:
                location = r.headers.get("location")
                if r.status_code in _REDIRECT_CODES and location:
                    url = urljoin(url, location)
                    continue
                if r.status_code != 200:
                    return None
                return _read_capped(r)
        except requests.RequestException:
            return None
    return None  # redirect chain longer than _MAX_REDIRECTS


def _load_scaled(data: bytes, max_cols: int):
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    max_w = max(64, max_cols * _CELL_PX[0])
    if img.width > max_w:
        img = img.resize((max_w, max(1, round(img.height * max_w / img.width))))
    if img.height > _MAX_PX_H:
        img = img.resize((max(1, round(img.width * _MAX_PX_H / img.height)), _MAX_PX_H))
    return img


def to_kitty(img) -> str:
    """Encode a PIL image as a kitty graphics-protocol escape (RGBA, chunked)."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    b64 = base64.standard_b64encode(rgba.tobytes()).decode("ascii")
    chunks = [b64[i : i + 4096] for i in range(0, len(b64), 4096)] or [""]
    parts = []
    for i, ch in enumerate(chunks):
        ctrl = f"a=T,f=32,s={w},v={h}," if i == 0 else ""
        ctrl += f"m={1 if i < len(chunks) - 1 else 0}"
        parts.append(f"\033_G{ctrl};{ch}\033\\")
    return "".join(parts) + "\n"


def to_sixel(img, max_colors: int = 256) -> str:
    """Encode a PIL image as a sixel data string."""
    from PIL import Image

    pal = img.convert("RGB").quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    w, h = pal.size
    px = pal.load()
    palette = pal.getpalette() or []
    ncolors = len(palette) // 3

    out = ["\033Pq", f'"1;1;{w};{h}']
    for i in range(ncolors):
        r, g, b = palette[3 * i : 3 * i + 3]
        out.append(f"#{i};2;{r * 100 // 255};{g * 100 // 255};{b * 100 // 255}")

    for top in range(0, h, 6):
        rows = min(6, h - top)
        cols = [[px[x, top + dy] for dy in range(rows)] for x in range(w)]
        band_colors = sorted({c for col in cols for c in col})
        for c in band_colors:
            out.append(f"#{c}")
            run_ch, run_n, line = None, 0, []
            for x in range(w):
                bits = 0
                for dy in range(rows):
                    if cols[x][dy] == c:
                        bits |= 1 << dy
                ch = chr(63 + bits)
                if ch == run_ch:
                    run_n += 1
                else:
                    if run_ch is not None:
                        line.append(f"!{run_n}{run_ch}" if run_n > 3 else run_ch * run_n)
                    run_ch, run_n = ch, 1
            if run_ch is not None:
                line.append(f"!{run_n}{run_ch}" if run_n > 3 else run_ch * run_n)
            out.append("".join(line))
            out.append("$")  # graphics CR: overlay next color on the same band
        out.append("-")      # next band
    out.append("\033\\")
    return "".join(out) + "\n"


def render_image(url: str, mode: str, max_cols: int) -> str | None:
    """Fetch, scale, and encode ``url`` for ``mode`` (kitty|sixel). ``None`` on any
    failure so the caller can fall back to a text placeholder."""
    if mode not in ("kitty", "sixel") or not available():
        return None
    data = _fetch(url)
    if not data:
        return None
    try:
        img = _load_scaled(data, max_cols)
        return to_kitty(img) if mode == "kitty" else to_sixel(img)
    except Exception:  # noqa: BLE001 — bad/unsupported image → placeholder
        return None
