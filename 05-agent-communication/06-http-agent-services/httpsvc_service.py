"""Ek agent = ek independent HTTP microservice (FastAPI).

Har agent service ye endpoints deti hai (yahi hamara chhota 'protocol' hai):
    GET  /health                -> liveness (load balancer / k8s probe)
    GET  /info                  -> naam + skills (self-description)
    POST /invoke  {input}       -> SYNC: jawab isi response mein
    POST /jobs    {input, callback_url?} -> ASYNC: 202 + job_id turant
    GET  /jobs/{id}             -> job status poll karo (queued/running/done/failed)

Auth: `Authorization: Bearer <token>` (shared secret). Real mein OAuth2/JWT/mTLS.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Callable

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

SkillHandler = Callable[[str], str]
CallbackPoster = Callable[[str, dict], None]


class InvokeIn(BaseModel):
    input: str


class JobIn(BaseModel):
    input: str
    callback_url: str | None = None


def _default_poster(url: str, payload: dict) -> None:
    try:
        httpx.post(url, json=payload, timeout=5)
    except httpx.HTTPError:
        pass  # webhook fail ho to bhi job result /jobs/{id} pe mil jaayega (poll fallback)


def create_agent_app(
    name: str,
    skills: list[str],
    handler: SkillHandler,
    *,
    token: str,
    callback_poster: CallbackPoster = _default_poster,
    register_with: str | None = None,  # registry URL; startup pe khud ko register karo
    public_url: str | None = None,
) -> FastAPI:
    jobs: dict[str, dict] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if register_with and public_url:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(f"{register_with}/register", json={"name": name, "url": public_url, "skills": skills},
                             headers={"Authorization": f"Bearer {token}"})
        yield

    app = FastAPI(title=f"{name} agent", lifespan=lifespan)
    app.state.jobs = jobs

    def auth(authorization: str = Header(default="")) -> None:
        if authorization != f"Bearer {token}":
            raise HTTPException(401, "missing or bad bearer token")

    @app.get("/health")
    def health():
        return {"status": "ok", "agent": name}

    @app.get("/info")
    def info():
        return {"name": name, "skills": skills}

    @app.post("/invoke", dependencies=[Depends(auth)])
    def invoke(body: InvokeIn):
        start = time.time()
        try:
            out = handler(body.input)
        except Exception as e:  # agent ka error -> 500 with message (client retry kar sakta hai)
            raise HTTPException(500, f"{type(e).__name__}: {e}")
        return {"agent": name, "output": out, "ms": int((time.time() - start) * 1000)}

    def _run_job(job_id: str) -> None:
        job = jobs[job_id]
        job["status"] = "running"
        try:
            job.update(status="done", output=handler(job["input"]))
        except Exception as e:
            job.update(status="failed", error=f"{type(e).__name__}: {e}")
        if job.get("callback_url"):
            callback_poster(job["callback_url"], {"job_id": job_id, **{k: job.get(k) for k in ("status", "output", "error")}})

    @app.post("/jobs", status_code=202, dependencies=[Depends(auth)])
    def submit(body: JobIn, bg: BackgroundTasks):
        job_id = uuid.uuid4().hex[:10]
        jobs[job_id] = {"id": job_id, "status": "queued", "input": body.input, "callback_url": body.callback_url}
        bg.add_task(_run_job, job_id)  # response pehle jaata hai, kaam baad mein
        return {"job_id": job_id, "status": "queued", "poll": f"/jobs/{job_id}"}

    @app.get("/jobs/{job_id}", dependencies=[Depends(auth)])
    def get_job(job_id: str):
        if job_id not in jobs:
            raise HTTPException(404, "no such job")
        j = jobs[job_id]
        return {k: j.get(k) for k in ("id", "status", "output", "error")}

    return app
