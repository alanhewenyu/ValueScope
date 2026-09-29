"""GET /mcp must answer 405, not hold open an SSE stream.

The server is stateless, so the standalone server-to-client stream can never
carry a message; holding it open made Glama's health check time out.
"""
import asyncio

from backend.mcp_server import MCPRequestMetaMiddleware


def _call(method, path):
    sent = []
    inner_called = []

    async def inner(scope, receive, send):
        inner_called.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": method, "path": path,
             "raw_path": path.encode(), "headers": [], "client": ("1.2.3.4", 0)}
    asyncio.run(MCPRequestMetaMiddleware(inner)(scope, receive, send))
    return sent[0]["status"], dict(sent[0]["headers"]), inner_called


def test_get_mcp_is_405():
    for path in ("/mcp", "/mcp/"):
        status, headers, inner = _call("GET", path)
        assert status == 405
        assert headers[b"allow"] == b"POST"
        assert inner == []


def test_post_mcp_passes_through():
    status, _, inner = _call("POST", "/mcp")
    assert status == 200
    assert inner == ["/mcp/"]
