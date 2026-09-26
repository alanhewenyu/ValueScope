"""An unsubstituted ${VAR} header must read as "no key", not as a bad key.

Marketplace connectors ship an mcp.json whose X-FMP-Key references a form
field users may leave blank (A-shares and HK need no key); some clients
forward the placeholder verbatim.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

from backend.mcp_server import _header_key, _query_key, _real_key


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


@pytest.mark.parametrize("headers, expected", [
    ({"x-fmp-key": "abc"}, ("abc", "x-fmp-key")),
    ({"authorization": "Bearer abc"}, ("abc", "authorization")),
    ({"authorization": "bearer   abc  "}, ("abc", "authorization")),
    # X-FMP-Key wins so existing setups are unaffected.
    ({"x-fmp-key": "abc", "authorization": "Bearer xyz"}, ("abc", "x-fmp-key")),
    # A blank or placeholder X-FMP-Key falls through to the bearer.
    ({"x-fmp-key": "${FMP_KEY}", "authorization": "Bearer xyz"}, ("xyz", "authorization")),
    ({"authorization": "Bearer ${FMP_KEY}"}, ("", "")),
    ({"authorization": "Basic abc"}, ("", "")),
    ({"authorization": "Bearer"}, ("", "")),
    ({}, ("", "")),
])
def test_header_key(headers, expected):
    assert _header_key(headers) == expected


@pytest.mark.parametrize("query, expected", [
    (b"fmp_key=abc", "abc"),
    (b"other=1&fmp_key=abc", "abc"),
    (b"fmp_key=%24%7BFMP_KEY%7D", ""),  # URL-encoded ${FMP_KEY}
    (b"fmp_key=", ""),
    (b"", ""),
])
def test_query_key(query, expected):
    assert _query_key(query) == expected
