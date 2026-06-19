"""Warm-engine daemon: a long-lived headless `servoshell` that `sr` reuses.

Cold-starting a debug `servoshell` per call costs ~2s. Start one once with
`sr-engine start` and every engine-tier read attaches to it over WebDriver (via
`$SERVO_WEBDRIVER`) instead of spawning its own — amortizing the cold start to ~0.
`sr` discovers a running daemon automatically; no env export needed.

    sr-engine start    # launch the warm engine
    sr-engine status   # is it up? where?
    sr-engine stop     # shut it down
    sr-engine env      # print `export SERVO_WEBDRIVER=…` for manual use
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    p = Path(base) / "servo-reader"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _engine_file() -> Path:
    return _state_dir() / "engine.json"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _read() -> dict | None:
    f = _engine_file()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return None


def _alive(info: dict | None) -> bool:
    if not info:
        return False
    pid = info.get("pid")
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return _port_open(info.get("host", "127.0.0.1"), int(info.get("port", 0)))


def endpoint() -> str | None:
    """``host:port`` of a live warm engine, or ``None``. Used by fetch for auto-attach."""
    info = _read()
    return f"{info['host']}:{info['port']}" if _alive(info) else None


def _find_binary() -> str | None:
    b = os.environ.get("SERVOSHELL")
    if b and Path(b).exists():
        return b
    try:
        from servo_agent.browser import find_servoshell

        p = find_servoshell()
        if p:
            return str(p)
    except Exception:  # noqa: BLE001 — discovery is best-effort
        pass
    return None


def start() -> dict:
    info = _read()
    if _alive(info):
        print(f"already running (pid {info['pid']}) at "
              f"{info['host']}:{info['port']}", file=sys.stderr)
        return info
    binary = _find_binary()
    if not binary:
        print("servoshell not found — set $SERVOSHELL=/path/to/servoshell", file=sys.stderr)
        raise SystemExit(2)
    host, port = "127.0.0.1", _free_port()
    log = open(_state_dir() / "engine.log", "ab")
    proc = subprocess.Popen(
        [binary, "--headless", "--webdriver", str(port), "about:blank"],
        stdout=log, stderr=log, start_new_session=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _port_open(host, port):
            break
        if proc.poll() is not None:
            print("servoshell exited during startup; see engine.log", file=sys.stderr)
            raise SystemExit(1)
        time.sleep(0.3)
    else:
        proc.terminate()
        print("WebDriver port never came up", file=sys.stderr)
        raise SystemExit(1)
    info = {"pid": proc.pid, "host": host, "port": port, "binary": binary}
    _engine_file().write_text(json.dumps(info))
    return info


def stop() -> None:
    info = _read()
    if not info:
        print("no daemon registered", file=sys.stderr)
        return
    pid = int(info["pid"])
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    _engine_file().unlink(missing_ok=True)
    print(f"stopped pid {pid}", file=sys.stderr)


def status() -> int:
    info = _read()
    if _alive(info):
        print(f"running  pid={info['pid']}  endpoint={info['host']}:{info['port']}  "
              f"binary={info.get('binary')}")
        return 0
    print("not running")
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "start":
        info = start()
        print(f"SERVO_WEBDRIVER={info['host']}:{info['port']}")
        print(f"warm engine up (pid {info['pid']}). sr uses it automatically.", file=sys.stderr)
        return 0
    if cmd == "stop":
        stop()
        return 0
    if cmd == "status":
        return status()
    if cmd == "env":
        ep = endpoint()
        if ep:
            print(f"export SERVO_WEBDRIVER={ep}")
            return 0
        print("# no warm engine; run: sr-engine start", file=sys.stderr)
        return 1
    print("usage: sr-engine {start|stop|status|env}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
