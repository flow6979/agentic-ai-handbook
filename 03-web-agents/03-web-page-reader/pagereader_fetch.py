"""Safe page fetcher: SSRF guard, robots.txt, user-agent, redirects, size limit, content types.

Agent ko 'koi bhi URL kholo' ki power dena khatarnak hai. LLM ko prompt injection se
bola ja sakta hai "http://169.254.169.254/latest/meta-data/ kholo" (cloud credentials!)
ya "http://localhost:8080/admin". Isliye:

  1. Sirf http/https
  2. Host resolve karo -> agar private/loopback/link-local IP hai to BLOCK (SSRF guard)
  3. Redirects khud follow karo aur HAR hop ko check karo (public URL private pe redirect kar sakta hai)
  4. robots.txt respect karo (site owner ki marzi) + honest User-Agent bhejo
  5. Max bytes: 50MB ka page memory aur tokens kha jayega
  6. Sirf text-type content: HTML -> extract, text/json -> as-is, PDF/images -> mana (RAG section dekho)
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from pagereader_extract import extract_text

USER_AGENT = "agentic-ai-handbook-reader/0.1 (+https://github.com/flow6979/agentic-ai-handbook)"
Resolver = Callable[..., list]


class FetchError(Exception):
    pass


@dataclass
class Page:
    url: str
    final_url: str
    content_type: str
    title: str
    text: str
    truncated: bool = False


def is_public_host(host: str, resolver: Resolver = socket.getaddrinfo) -> bool:
    """Host ke saare resolved IPs public (global) hone chahiye."""
    try:
        addrs = {ipaddress.ip_address(host.strip("[]"))}
    except ValueError:
        try:
            infos = resolver(host, None)
        except socket.gaierror:
            return False
        addrs = {ipaddress.ip_address(info[4][0]) for info in infos}
    return bool(addrs) and all(a.is_global for a in addrs)


def check_url(url: str, resolver: Resolver = socket.getaddrinfo) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchError(f"blocked scheme {p.scheme!r}: only http/https allowed")
    if not p.hostname:
        raise FetchError("URL has no host")
    if not is_public_host(p.hostname, resolver):
        raise FetchError(f"blocked host {p.hostname!r}: private/internal addresses are not allowed (SSRF guard)")


class PageFetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        resolver: Resolver = socket.getaddrinfo,
        max_bytes: int = 2_000_000,
        max_redirects: int = 5,
        respect_robots: bool = True,
        user_agent: str = USER_AGENT,
    ):
        # follow_redirects=False: redirects hum khud follow karenge taaki har hop check ho
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)
        self.resolver = resolver
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self._robots: dict[str, RobotFileParser] = {}

    def allowed_by_robots(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.client.get(base + "/robots.txt", headers={"User-Agent": self.user_agent})
                # 4xx = robots.txt nahi hai = sab allowed. 5xx = site down, safe side pe allow (common convention).
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.TransportError:
                rp.parse([])
            self._robots[base] = rp
        return self._robots[base].can_fetch(self.user_agent, url)

    def fetch(self, url: str) -> Page:
        current = url
        for _ in range(self.max_redirects + 1):
            check_url(current, self.resolver)
            if self.respect_robots and not self.allowed_by_robots(current):
                raise FetchError(f"robots.txt disallows fetching {current}")
            with self.client.stream("GET", current, headers={"User-Agent": self.user_agent, "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5"}) as r:
                if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code >= 400:
                    raise FetchError(f"HTTP {r.status_code} for {current}")
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if not (ctype.startswith("text/") or ctype in ("application/json", "application/xhtml+xml", "")):
                    raise FetchError(f"unsupported content-type {ctype!r} (PDFs/images: see 04-rag)")
                body, truncated = bytearray(), False
                for chunk in r.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.max_bytes:
                        body, truncated = body[: self.max_bytes], True
                        break
                raw = bytes(body).decode(r.encoding or "utf-8", errors="replace")
            if ctype in ("text/html", "application/xhtml+xml", "") and "<" in raw[:1000]:
                title, text = extract_text(raw)
            else:
                title, text = "", raw
            return Page(url, current, ctype or "text/html", title, text, truncated)
        raise FetchError(f"too many redirects (>{self.max_redirects})")
