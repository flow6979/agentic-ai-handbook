"""Chhota HTTP layer jo normal Python AUR browser (Pyodide) dono mein chalta hai.

Normal Python (CPython) mein: httpx se request.
Browser mein (Pyodide, sys.platform == "emscripten"): sockets nahi hote, isliye Web Worker
ke andar synchronous XMLHttpRequest use karte hain. Worker mein sync XHR allowed hai, aur
isse hamara poora agentkit (jo sync code hai) bina badle browser mein chal jata hai.

Tests ya custom setups ke liye `set_transport(fn)` se apna transport laga sakte ho.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable

IN_BROWSER = sys.platform == "emscripten"


@dataclass
class HTTPResponse:
    status: int
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


class TransportError(Exception):
    """Network tak pahunch hi nahi paaye (DNS, CORS, offline, timeout)."""


Transport = Callable[[str, str, dict[str, str], str | None, float], HTTPResponse]


def _httpx_transport(method: str, url: str, headers: dict[str, str], body: str | None, timeout: float) -> HTTPResponse:
    import httpx

    try:
        r = httpx.request(method, url, headers=headers, content=body, timeout=timeout)
    except httpx.TransportError as e:
        raise TransportError(str(e)) from e
    return HTTPResponse(r.status_code, r.text)


def _xhr_transport(method: str, url: str, headers: dict[str, str], body: str | None, timeout: float) -> HTTPResponse:
    from js import XMLHttpRequest  # type: ignore[import-not-found]  # sirf Pyodide mein milta hai

    xhr = XMLHttpRequest.new()
    xhr.open(method, url, False)  # False = synchronous (sirf Web Worker mein allowed)
    for k, v in headers.items():
        xhr.setRequestHeader(k, v)
    try:
        xhr.send(body)
    except Exception as e:  # CORS block ya network down: browser status 0 deta hai / throw karta hai
        raise TransportError(f"browser request failed: {e}") from e
    if xhr.status == 0:
        raise TransportError("browser request failed (network error or CORS blocked)")
    return HTTPResponse(int(xhr.status), str(xhr.responseText))


_transport: Transport = _xhr_transport if IN_BROWSER else _httpx_transport


def set_transport(fn: Transport | None) -> None:
    """Transport badlo (None = default wapas)."""
    global _transport
    _transport = fn or (_xhr_transport if IN_BROWSER else _httpx_transport)


def request(method: str, url: str, *, headers: dict[str, str] | None = None, json_body: Any = None,
            timeout: float = 60.0) -> HTTPResponse:
    headers = dict(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body)
        headers.setdefault("Content-Type", "application/json")
    return _transport(method, url, headers, body, timeout)


def post_json(url: str, body: Any, *, headers: dict[str, str] | None = None, timeout: float = 60.0) -> HTTPResponse:
    return request("POST", url, headers=headers, json_body=body, timeout=timeout)


def get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 30.0) -> HTTPResponse:
    return request("GET", url, headers=headers, timeout=timeout)
