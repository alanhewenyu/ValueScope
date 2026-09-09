"""An unsubstituted ${VAR} header must read as "no key", not as a bad key.

Marketplace connectors ship an mcp.json whose X-FMP-Key references a form
field users may leave blank (A-shares and HK need no key); some clients
forward the placeholder verbatim.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

from backend.mcp_server import _real_key


@pytest.mark.parametrize("value", [
    "${VALUESCOPE_FMP_KEY}",
    "  ${FMP_KEY}  ",
    "${}",
])
def test_placeholder_reads_as_absent(value):
    assert _real_key(value) == ""


@pytest.mark.parametrize("value, expected", [
    ("abc123", "abc123"),
    ("  abc123  ", "abc123"),
    ("", ""),
    (None, ""),
    # Only a whole-string placeholder is dropped — a real key is never
    # silently discarded because it happens to contain a brace.
    ("${notclosed", "${notclosed"),
    ("key${x}", "key${x}"),
])
def test_real_keys_survive(value, expected):
    assert _real_key(value) == expected
