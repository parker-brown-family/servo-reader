"""Warm-engine daemon: stopping an engine for real. No engine, no network."""

from __future__ import annotations

import json
import signal

import pytest

import servo_reader.daemon as daemon


@pytest.fixture
def registered(tmp_path, monkeypatch):
    """A registered engine at pid 4242, with time that passes instantly."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    daemon._engine_file().write_text(json.dumps({"pid": 4242, "host": "127.0.0.1",
                                                 "port": 7999, "binary": "servoshell"}))
    clock = {"now": 0.0}

    def tick() -> float:
        clock["now"] += 0.05
        return clock["now"]

    monkeypatch.setattr(daemon.time, "monotonic", tick)
    monkeypatch.setattr(daemon.time, "sleep", lambda _s: None)
    monkeypatch.setattr(daemon, "_is_engine", lambda _pid: True)
    sent: list[int] = []
    monkeypatch.setattr(daemon.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(daemon.os, "killpg", lambda _pg, sig: sent.append(sig))
    return sent


class _Engine:
    """Exits on the shutdown route, on SIGTERM or on SIGKILL, as configured."""

    def __init__(self, monkeypatch, exits_on: set[str], sent: list[int]) -> None:
        self.alive = True
        self.routes: list[str] = []

        def urlopen(req, timeout=None):
            self.routes.append(req.full_url)
            if "route" in exits_on:
                self.alive = False

            class _Answer:
                def read(self):
                    return b'{"value":null}'

            return _Answer()

        def killpg(_pg, sig):
            sent.append(sig)
            if {signal.SIGTERM: "term", signal.SIGKILL: "kill"}[sig] in exits_on:
                self.alive = False

        monkeypatch.setattr(daemon.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(daemon.os, "killpg", killpg)
        monkeypatch.setattr(daemon, "_gone", lambda _pid: not self.alive)


def test_stop_asks_servo_to_shut_down_first(registered, monkeypatch) -> None:
    engine = _Engine(monkeypatch, {"route"}, registered)

    assert daemon.stop() == 0

    assert engine.routes == ["http://127.0.0.1:7999/session/none/servo/shutdown"]
    assert registered == [], "an engine that quit through the route needs no signal"
    assert not daemon._engine_file().exists()


def test_stop_kills_an_engine_that_ignores_the_route_and_sigterm(registered, monkeypatch) -> None:
    """Servo 0.7 catches SIGTERM and never exits headless."""
    _Engine(monkeypatch, {"kill"}, registered)

    assert daemon.stop() == 0

    assert registered == [signal.SIGTERM, signal.SIGKILL]
    assert not daemon._engine_file().exists()


def test_stop_keeps_the_record_while_the_engine_still_runs(registered, monkeypatch) -> None:
    _Engine(monkeypatch, set(), registered)

    assert daemon.stop() == 1

    assert daemon._engine_file().exists(), "an engine still running must stay registered"


def test_stop_never_signals_a_pid_that_is_no_longer_the_engine(registered, monkeypatch) -> None:
    engine = _Engine(monkeypatch, set(), registered)
    monkeypatch.setattr(daemon, "_is_engine", lambda _pid: False)

    assert daemon.stop() == 0

    assert registered == [] and engine.routes == []
    assert not daemon._engine_file().exists()


def test_status_reports_the_engine_memory(registered, monkeypatch, capsys) -> None:
    monkeypatch.setattr(daemon, "_alive", lambda _info: True)
    monkeypatch.setattr(daemon, "memory_mb", lambda _pid: 812)

    assert daemon.status() == 0

    assert "memory=812 MB" in capsys.readouterr().out


def test_status_says_unknown_when_memory_cannot_be_read(registered, monkeypatch, capsys) -> None:
    monkeypatch.setattr(daemon, "_alive", lambda _info: True)
    monkeypatch.setattr(daemon, "memory_mb", lambda _pid: None)

    daemon.status()

    assert "memory=unknown" in capsys.readouterr().out
