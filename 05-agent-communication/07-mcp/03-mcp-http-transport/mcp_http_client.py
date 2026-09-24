"""Remote MCP server se connect karna: URL + auth header.

`Client("http://.../mcp")` seedha kaam karta hai jab auth na ho. Headers chahiye to
apna httpx client banao aur `streamable_http_client(url, http_client=...)` transport do.
(Note: mcp SDK 2.x andar `httpx2` package use karta hai, isliye wahi import.)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def http_transport(url: str, token: str | None):
    """MCPBridge / Client ko dene layak transport (headers ke saath)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return streamable_http_client(url, http_client=httpx2.AsyncClient(headers=headers, timeout=30))


@asynccontextmanager
async def connect(url: str, token: str | None, mode: str = "auto"):
    """mode='auto' -> naya 2026-07-28 stateless protocol try, warna purana initialize handshake.
    mode='legacy' -> seedha initialize handshake (2025-11-25)."""
    async with Client(http_transport(url, token), mode=mode) as c:
        yield c
