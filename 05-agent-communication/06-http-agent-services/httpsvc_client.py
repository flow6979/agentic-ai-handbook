"""AgentClient: dusri agent services ko HTTP pe call karne ka resilient client.

Network pe baat karne ke 4 niyam (sab yahan implement hain):
  1. Timeout hamesha lagao  (warna ek atki service tumhe bhi atka degi)
  2. Retry sirf safe cases pe (timeout, connection error, 5xx), 4xx pe NAHI
  3. Backoff ke saath retry (1x, 2x, 4x...)
  4. Auth header har request pe
"""
from __future__ import annotations

import time
from typing import Callable

import httpx

HttpFactory = Callable[[str], httpx.Client]


class RemoteAgentError(Exception):
    pass


class AgentClient:
    def __init__(self, registry_url: str, token: str, *, http_factory: HttpFactory | None = None,
                 timeout: float = 30.0, retries: int = 2, backoff: float = 0.5, sleep=time.sleep):
        self.registry_url = registry_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep
        # Tests mein factory TestClient deti hai; real mein normal httpx.Client
        self._factory = http_factory or (lambda base: httpx.Client(base_url=base, timeout=timeout))
        self._clients: dict[str, httpx.Client] = {}

    def _http(self, base_url: str) -> httpx.Client:
        base_url = base_url.rstrip("/")
        if base_url not in self._clients:
            self._clients[base_url] = self._factory(base_url)
        return self._clients[base_url]

    def _request(self, method: str, base_url: str, path: str, **kw) -> dict | list:
        headers = {"Authorization": f"Bearer {self.token}"}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self._http(base_url).request(method, path, headers=headers, **kw)  # timeout client pe set hai (factory)
                if r.status_code >= 500:
                    raise RemoteAgentError(f"{base_url}{path} -> {r.status_code}: {r.text[:200]}")
                if r.status_code >= 400:  # client error: retry se theek nahi hoga
                    raise PermissionError(f"{base_url}{path} -> {r.status_code}: {r.text[:200]}") if r.status_code in (401, 403) \
                        else ValueError(f"{base_url}{path} -> {r.status_code}: {r.text[:200]}")
                return r.json()
            except (httpx.TimeoutException, httpx.TransportError, RemoteAgentError) as e:
                last = e
                if attempt < self.retries:
                    self._sleep(self.backoff * 2**attempt)
        raise RemoteAgentError(f"giving up after {self.retries + 1} attempts: {last}")

    # --- discovery ---------------------------------------------------------
    def discover(self, skill: str) -> list[dict]:
        return self._request("GET", self.registry_url, "/agents", params={"skill": skill})  # type: ignore[return-value]

    def skills(self) -> dict[str, list[str]]:
        return {a["name"]: a["skills"] for a in self._request("GET", self.registry_url, "/agents")}  # type: ignore[union-attr]

    # --- sync --------------------------------------------------------------
    def invoke(self, agent_url: str, text: str) -> str:
        return self._request("POST", agent_url, "/invoke", json={"input": text})["output"]  # type: ignore[index]

    def invoke_skill(self, skill: str, text: str) -> str:
        found = self.discover(skill)
        if not found:
            raise LookupError(f"no agent offers skill {skill!r}")
        return self.invoke(found[0]["url"], text)

    # --- async job ---------------------------------------------------------
    def submit_job(self, agent_url: str, text: str, callback_url: str | None = None) -> str:
        return self._request("POST", agent_url, "/jobs", json={"input": text, "callback_url": callback_url})["job_id"]  # type: ignore[index]

    def get_job(self, agent_url: str, job_id: str) -> dict:
        return self._request("GET", agent_url, f"/jobs/{job_id}")  # type: ignore[return-value]

    def wait_for_job(self, agent_url: str, job_id: str, *, poll_every: float = 0.5, max_wait: float = 60) -> dict:
        deadline = time.monotonic() + max_wait
        while True:
            job = self.get_job(agent_url, job_id)
            if job["status"] in ("done", "failed"):
                return job
            if time.monotonic() > deadline:
                raise TimeoutError(f"job {job_id} still {job['status']} after {max_wait}s")
            self._sleep(poll_every)
