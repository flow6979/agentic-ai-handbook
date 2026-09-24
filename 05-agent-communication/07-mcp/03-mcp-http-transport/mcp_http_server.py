"""Wahi notes server, lekin network pe: Streamable HTTP (+ legacy SSE) + bearer-token auth.

    python mcp_http_server.py                         # http://127.0.0.1:8765/mcp  (token: MCP_TOKEN env, default dev-token)
    python mcp_http_server.py --stateless --json      # har request independent, SSE nahi, plain JSON response
    python mcp_http_server.py --transport sse         # purana (deprecated) HTTP+SSE transport: GET /sse + POST /messages/

stdio vs HTTP:
    stdio -> server host ke laptop pe subprocess. Ek user, koi network, koi auth nahi.
    HTTP  -> server kahin bhi (cloud). Bahut users, isliye AUTH zaroori.

Auth yahan jaan-boojh ke simple hai (static bearer token) taaki concept dikhe.
Production mein MCP spec OAuth 2.1 bolta hai: server = "resource server", token kisi
authorization server se aata hai; SDK mein `token_verifier=` / `auth=` se wire hota hai.
"""
from __future__ import annotations

import argparse
import hmac
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-mcp-server-stdio"))

from mcp_notes_server import build_server  # noqa: E402

DEFAULT_TOKEN = "dev-token"


class BearerAuthMiddleware:
    """Pure ASGI middleware: har HTTP request pe `Authorization: Bearer <token>` check.

    Galat/missing token -> 401 + `WWW-Authenticate` header (OAuth-style; MCP clients isi header
    se discover karte hain ki auth kahan se lena hai).
    """

    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") == "/health":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"")
        ok = auth.startswith(b"Bearer ") and hmac.compare_digest(auth[7:], self.token)  # timing-safe compare
        if not ok:
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="mcp", error="invalid_token"'),
            ]})
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        await self.app(scope, receive, send)


def build_http_app(db_path: str | None = None, *, token: str | None = None, transport: str = "streamable-http",
                   stateless: bool = False, json_response: bool = False):
    server = build_server(db_path)
    if transport == "sse":
        app = server.sse_app()  # legacy: 2024-11-05 era transport
    else:
        app = server.streamable_http_app(stateless_http=stateless, json_response=json_response)
    return BearerAuthMiddleware(app, token or os.getenv("MCP_TOKEN", DEFAULT_TOKEN))


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")  # 0.0.0.0 tabhi jab sach mein bahar expose karna ho
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--transport", choices=["streamable-http", "sse"], default="streamable-http")
    ap.add_argument("--stateless", action="store_true", help="no Mcp-Session-Id; easy horizontal scaling")
    ap.add_argument("--json", action="store_true", help="reply with application/json instead of an SSE stream")
    ap.add_argument("--db", default=os.path.join(HERE, "notes_http.sqlite3"))
    ap.add_argument("--offline", action="store_true", help="accepted for consistency; the server never calls an LLM")
    args = ap.parse_args()
    app = build_http_app(args.db, transport=args.transport, stateless=args.stateless, json_response=args.json)
    path = "/sse" if args.transport == "sse" else "/mcp"
    print(f"MCP {args.transport} server on http://{args.host}:{args.port}{path}  (token from MCP_TOKEN)", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
