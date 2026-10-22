"""Warm-engine daemon: a long-lived headless `servoshell` that `sr` reuses.

Cold-starting a debug `servoshell` per call costs ~2s. Start one once with
`sr-engine start` and every engine-tier read attaches to it over WebDriver (via
`$SERVO_WEBDRIVER`) instead of spawning its own — amortizing the cold start to ~0.
`sr` discovers a running daemon automatically; no env export needed.

    sr-engine start    # launch the warm engine
    sr-engine status   # is it up? where? how much memory?
    sr-engine stop     # shut it down
    sr-engine restart  # stop it, then start a fresh one
    sr-engine env      # print `export SERVO_WEBDRIVER=…` for manual use

Servo's memory climbs with every page it opens in one window (Servo 0.7.0 went
from 334 MB to 5.3 GB over 100 pages), so a warm engine that has served many
reads is worth restarting; `status` shows its memory.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
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
        print("servoshell not found — run `servo-agent install-servo` (Linux) or set "
              "$SERVOSHELL=/path/to/servoshell", file=sys.stderr)
        raise SystemExit(2)
    host, port = "127.0.0.1", _free_port()
    log = open(_state_dir() / "engine.log", "ab")
    # --temporary-storage: a profile of the engine's own, instead of the one every
    # servoshell on the machine shares in ~/.config/servo/default.
    proc = subprocess.Popen(
        [binary, "--headless", "--temporary-storage", "--webdriver", str(port), "about:blank"],
        stdout=log, stderr=log, start_new_session=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _port_open(host, port):
            break
        if proc.poll() is not None:
            print("servoshell exited during startup; see engine.log", file=sys.stderr)
            raise SystemExit(1)
        time.sleep(0.1)
    else:
        proc.kill()
        print("WebDriver port never came up", file=sys.stderr)
        raise SystemExit(1)
    info = {"pid": proc.pid, "host": host, "port": port, "binary": binary}
    _engine_file().write_text(json.dumps(info))
    return info


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False  # it exists; it just isn't ours to signal
    return False


def _wait_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not _gone(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _is_engine(pid: int) -> bool | None:
    """Is `pid` a servoshell? None when this system can't say (no /proc)."""
    if not Path("/proc/self").exists():
        return None
    try:
        argv0 = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0]
    except FileNotFoundError:
        return False
    except OSError:
        return None
    return "servoshell" in Path(argv0.decode(errors="replace")).name


def memory_mb(pid: int) -> int | None:
    """The engine's PSS in MB from /proc; None when unknown."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return round(int(line.split()[1]) / 1024)
    except (OSError, ValueError):
        return None
    return None


def stop() -> int:
    """Stop the registered engine, and unregister it only once it has exited.

    Servo's own WebDriver route, DELETE /session/{id}/servo/shutdown, comes
    first: Servo 0.7 catches SIGTERM and never exits when headless, so SIGTERM
    alone used to leave the engine running, unregistered, with nothing left to
    stop it. With no session open, the route takes any id. SIGTERM and then
    SIGKILL follow, and only for a process that is still a servoshell, so a stale
    record whose pid now belongs to something else is never signalled.
    """
    info = _read()
    if not info:
        print("no daemon registered", file=sys.stderr)
        return 0
    pid = int(info["pid"])
    if _gone(pid) or _is_engine(pid) is False:
        _engine_file().unlink(missing_ok=True)
        print(f"pid {pid} was no longer the engine; unregistered it", file=sys.stderr)
        return 0
    how = None
    url = f"http://{info.get('host', '127.0.0.1')}:{info.get('port')}/session/none/servo/shutdown"
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=5).read()
    except Exception:  # noqa: BLE001 — a refused route falls through to signals
        pass
    if _wait_gone(pid, 2.0):
        how = "shut down"
    else:
        for sig, label in ((signal.SIGTERM, "terminated"), (signal.SIGKILL, "killed")):
            try:
                os.killpg(os.getpgid(pid), sig)
            except OSError:
                try:
                    os.kill(pid, sig)
                except OSError:
                    pass
            if _wait_gone(pid, 2.0):
                how = label
                break
    if how is None:
        print(f"pid {pid} is still running; left it registered", file=sys.stderr)
        return 1
    _engine_file().unlink(missing_ok=True)
    print(f"stopped pid {pid} ({how})", file=sys.stderr)
    return 0


def status() -> int:
    info = _read()
    if _alive(info):
        mb = memory_mb(int(info["pid"]))
        memory = f"{mb} MB" if mb is not None else "unknown"
        print(f"running  pid={info['pid']}  endpoint={info['host']}:{info['port']}  "
              f"memory={memory}  binary={info.get('binary')}")
        return 0
    print("not running")
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd in ("start", "restart"):
        if cmd == "restart" and stop() != 0:
            return 1
        info = start()
        print(f"SERVO_WEBDRIVER={info['host']}:{info['port']}")
        print(f"warm engine up (pid {info['pid']}). sr uses it automatically.", file=sys.stderr)
        return 0
    if cmd == "stop":
        return stop()
    if cmd == "status":
        return status()
    if cmd == "env":
        ep = endpoint()
        if ep:
            print(f"export SERVO_WEBDRIVER={ep}")
            return 0
        print("# no warm engine; run: sr-engine start", file=sys.stderr)
        return 1
    print("usage: sr-engine {start|stop|restart|status|env}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
