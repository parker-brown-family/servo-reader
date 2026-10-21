"""The image lane only fetches from public addresses — DNS and HTTP are stubbed.

Kept apart from test_images.py, whose encoder tests skip the module without Pillow;
these must run everywhere.
"""

from __future__ import annotations

import io
import socket

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from servo_reader import images

PUBLIC = "93.184.215.14"


def _response(status: int, body: bytes = b"", headers: dict | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.headers = CaseInsensitiveDict(headers or {})
    r.raw = io.BytesIO(body)
    return r


@pytest.fixture
def net(monkeypatch):
    """Stub DNS (``hosts``: name → addresses) and HTTP (``routes``: URL → response).

    Every URL handed to requests.get is recorded in ``calls``, so a test can prove
    that a refused destination was never contacted.
    """
    hosts: dict[str, list[str]] = {}
    routes: dict[str, requests.Response] = {}
    calls: list[str] = []

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host not in hosts:
            raise socket.gaierror(f"no such host: {host}")
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "",
             (ip, port))
            for ip in hosts[host]
        ]

    def fake_get(url, **kwargs):
        assert kwargs.get("allow_redirects") is False, "redirects must be followed by hand"
        calls.append(url)
        return routes[url]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(requests, "get", fake_get)
    return hosts, routes, calls


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1", "::1",                  # loopback
        "10.0.0.1", "172.16.5.4", "192.168.0.10", "fc00::1",  # private
        "169.254.169.254", "fe80::1",        # link-local, incl. cloud metadata
        "0.0.0.0", "::",                     # unspecified
        "224.0.0.251", "ff02::1",            # multicast
        "240.0.0.1",                         # reserved
        "100.100.100.200",                   # shared address space, not global
        "::ffff:127.0.0.1",                  # IPv4-mapped loopback
    ],
)
def test_internal_addresses_are_not_public(addr):
    assert not images._is_public_ip(addr)


@pytest.mark.parametrize("addr", [PUBLIC, "2606:4700::6810:84e5", "::ffff:8.8.8.8"])
def test_global_addresses_are_public(addr):
    assert images._is_public_ip(addr)


def test_metadata_endpoint_is_never_requested(net):
    hosts, _, calls = net
    hosts["169.254.169.254"] = ["169.254.169.254"]
    assert images._fetch("http://169.254.169.254/latest/meta-data/") is None
    assert calls == []


def test_name_resolving_to_loopback_is_refused(net):
    hosts, _, calls = net
    hosts["localhost"] = ["127.0.0.1", "::1"]
    assert images._fetch("http://localhost:8080/admin.png") is None
    assert calls == []


def test_one_private_address_among_several_refuses_the_host(net):
    hosts, _, calls = net
    hosts["mixed.example"] = [PUBLIC, "10.0.0.7"]
    assert images._fetch("https://mixed.example/a.png") is None
    assert calls == []


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://img.example/a.png",
        "data:image/png;base64,AAAA",
        "//img.example/a.png",
    ],
)
def test_only_http_and_https_are_fetched(net, url):
    hosts, _, calls = net
    hosts["img.example"] = [PUBLIC]
    assert images._fetch(url) is None
    assert calls == []


def test_unresolvable_host_is_refused(net):
    _, _, calls = net
    assert images._fetch("https://nowhere.invalid/a.png") is None
    assert calls == []


def test_public_image_is_fetched(net):
    hosts, routes, calls = net
    hosts["img.example"] = [PUBLIC]
    routes["https://img.example/a.png"] = _response(200, b"PNGDATA")
    assert images._fetch("https://img.example/a.png") == b"PNGDATA"
    assert calls == ["https://img.example/a.png"]


def test_redirect_to_an_internal_address_is_not_followed(net):
    hosts, routes, calls = net
    hosts["img.example"] = [PUBLIC]
    hosts["127.0.0.1"] = ["127.0.0.1"]
    routes["https://img.example/a.png"] = _response(
        302, headers={"Location": "http://127.0.0.1:8080/admin"}
    )
    assert images._fetch("https://img.example/a.png") is None
    assert calls == ["https://img.example/a.png"]


def test_redirect_to_a_name_resolving_inward_is_not_followed(net):
    hosts, routes, calls = net
    hosts["img.example"] = [PUBLIC]
    hosts["internal.example"] = ["192.168.1.20"]
    routes["https://img.example/a.png"] = _response(
        301, headers={"Location": "https://internal.example/a.png"}
    )
    assert images._fetch("https://img.example/a.png") is None
    assert calls == ["https://img.example/a.png"]


def test_relative_redirect_is_resolved_then_fetched(net):
    hosts, routes, calls = net
    hosts["img.example"] = [PUBLIC]
    routes["https://img.example/a.png"] = _response(302, headers={"Location": "/b.png"})
    routes["https://img.example/b.png"] = _response(200, b"PNGDATA")
    assert images._fetch("https://img.example/a.png") == b"PNGDATA"
    assert calls == ["https://img.example/a.png", "https://img.example/b.png"]


def test_redirect_chain_is_capped(net):
    hosts, routes, calls = net
    hosts["img.example"] = [PUBLIC]
    for i in range(images._MAX_REDIRECTS + 2):
        routes[f"https://img.example/{i}.png"] = _response(
            307, headers={"Location": f"/{i + 1}.png"}
        )
    assert images._fetch("https://img.example/0.png") is None
    assert len(calls) == images._MAX_REDIRECTS + 1


def test_oversized_image_is_skipped(net, monkeypatch):
    hosts, routes, _ = net
    monkeypatch.setattr(images, "_MAX_BYTES", 10)
    hosts["img.example"] = [PUBLIC]
    routes["https://img.example/big.png"] = _response(200, b"x" * 11)
    assert images._fetch("https://img.example/big.png") is None


def test_error_status_returns_none(net):
    hosts, routes, _ = net
    hosts["img.example"] = [PUBLIC]
    routes["https://img.example/gone.png"] = _response(404)
    assert images._fetch("https://img.example/gone.png") is None
