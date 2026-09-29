# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""The default-timeout patch is what keeps a hung upstream socket from holding
a cold-fetch slot forever (see backend/http_timeout.py). Without it akshare's
timeout-less calls took every profile/financials endpoint down for hours.
"""

import requests
from requests.adapters import HTTPAdapter

from backend import http_timeout


def _record_timeouts(monkeypatch):
    """Capture the timeout each adapter send would use, without any network."""
    seen = []
    original = HTTPAdapter.send

    def fake_send(self, request, **kwargs):
        seen.append(kwargs.get("timeout"))
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = None
        resp.request = request
        return resp

    # Patch the real network call underneath whatever wrapper is installed.
    monkeypatch.setattr(http_timeout, "_installed", False, raising=False)
    monkeypatch.setattr(HTTPAdapter, "send", fake_send, raising=True)
    http_timeout.install()
    monkeypatch.setattr(http_timeout, "_installed", False, raising=False)
    return seen, original


def test_default_timeout_injected_when_caller_passes_none(monkeypatch):
    seen, _ = _record_timeouts(monkeypatch)

    requests.get("http://example.invalid/thing")

    assert seen == [(http_timeout.CONNECT_TIMEOUT, http_timeout.READ_TIMEOUT)]


def test_explicit_timeout_is_preserved(monkeypatch):
    seen, _ = _record_timeouts(monkeypatch)

    # The deliberately long calls (DeepSeek 300s) must not be shortened.
    requests.get("http://example.invalid/thing", timeout=300)

    assert seen == [300]


def test_explicit_tuple_timeout_is_preserved(monkeypatch):
    seen, _ = _record_timeouts(monkeypatch)

    requests.get("http://example.invalid/thing", timeout=(3, 7))

    assert seen == [(3, 7)]


def test_install_is_idempotent(monkeypatch):
    """Repeated installs must not stack wrappers on top of each other."""
    calls = []
    original = HTTPAdapter.send

    def fake_send(self, request, **kwargs):
        calls.append(kwargs.get("timeout"))
        resp = requests.Response()
        resp.status_code = 200
        resp.request = request
        return resp

    monkeypatch.setattr(HTTPAdapter, "send", fake_send, raising=True)
    monkeypatch.setattr(http_timeout, "_installed", False, raising=False)

    assert http_timeout.install() is True
    patched_once = HTTPAdapter.send
    assert http_timeout.install() is True
    assert HTTPAdapter.send is patched_once

    monkeypatch.setattr(http_timeout, "_installed", False, raising=False)
    monkeypatch.setattr(HTTPAdapter, "send", original, raising=True)
