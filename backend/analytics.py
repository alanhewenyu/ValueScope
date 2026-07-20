"""Server-side Google Analytics (GA4 Measurement Protocol).

The web frontend reports events via the browser gtag.js snippet, but MCP
calls never touch a browser — they're machine-to-machine API requests. This
module sends the same GA4 account server-side events so MCP usage shows up
alongside web traffic.

Fire-and-forget: events are sent on a daemon thread with a short timeout and
all errors swallowed, so analytics can never slow down or break a tool call.
Requires GA_API_SECRET in the environment; without it this is a silent no-op.
"""

import hashlib
import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "G-V43CZJ8B32")
GA_API_SECRET = os.environ.get("GA_API_SECRET", "")
_GA_ENDPOINT = "https://www.google-analytics.com/mp/collect"
_CLIENT_ID_SALT = os.environ.get("GA_CLIENT_ID_SALT", "valuescope-mcp")

# The owner's own MCP calls come through the Measurement Protocol from the
# server's egress IP, so GA's IP-based internal-traffic rule (which only sees
# gtag hits) can't catch them. Tag events from these caller IPs with
# traffic_type=internal so the active Internal Traffic data filter excludes
# them — keeping the north-star metric (unique external mcp_run_dcf callers)
# clean. Comma-separated list, e.g. "89.187.185.11,1.2.3.4".
_INTERNAL_IPS = {
    ip.strip() for ip in os.environ.get("VS_INTERNAL_IPS", "").split(",") if ip.strip()
}


def _client_id(ip: str) -> str:
    """Stable pseudonymous client_id per IP (hashed, no raw IP sent to GA)."""
    digest = hashlib.sha256(f"{_CLIENT_ID_SALT}:{ip}".encode()).hexdigest()
    # GA4 client_id convention: "<random>.<timestamp>"; a stable hash works.
    return f"{int(digest[:12], 16)}.0"


def _post(payload: dict) -> None:
    try:
        requests.post(
            _GA_ENDPOINT,
            params={"measurement_id": GA_MEASUREMENT_ID, "api_secret": GA_API_SECRET},
            json=payload,
            timeout=2,
        )
    except Exception as e:  # never let analytics surface
        logger.debug("GA MP send failed: %s", e)


def track(event_name: str, ip: str, params: dict | None = None) -> None:
    """Queue a GA4 event on a daemon thread. No-op without GA_API_SECRET."""
    if not GA_API_SECRET:
        return
    # GA4 needs engagement_time_msec + session_id for events to surface in
    # standard reports (not just DebugView / realtime).
    event_params = {"engagement_time_msec": "1", "session_id": _client_id(ip)}
    if ip in _INTERNAL_IPS:
        event_params["traffic_type"] = "internal"
    for k, v in (params or {}).items():
        if v is not None:
            event_params[k] = v
    payload = {
        "client_id": _client_id(ip),
        "events": [{"name": event_name, "params": event_params}],
    }
    threading.Thread(target=_post, args=(payload,), daemon=True).start()
