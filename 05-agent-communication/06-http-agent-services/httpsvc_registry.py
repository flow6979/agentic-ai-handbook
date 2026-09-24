"""Service registry: 'kaun sa agent kahan hai aur kya kar sakta hai'.

Agents startup pe khud ko register karte hain. Orchestrator skill se dhoondta hai:
    GET /agents?skill=summarize  ->  [{"name": "summarizer", "url": "http://...:8001", ...}]

Real world: Consul, Eureka, Kubernetes Service DNS, ya A2A ka Agent Card (/.well-known/agent.json).
"""
from __future__ import annotations

import time

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel


class Registration(BaseModel):
    name: str
    url: str
    skills: list[str]


def create_registry_app(token: str) -> FastAPI:
    app = FastAPI(title="agent registry")
    agents: dict[str, dict] = {}
    app.state.agents = agents

    def auth(authorization: str = Header(default="")) -> None:
        if authorization != f"Bearer {token}":
            raise HTTPException(401, "missing or bad bearer token")

    @app.post("/register", dependencies=[Depends(auth)])
    def register(r: Registration):
        agents[r.name] = {**r.model_dump(), "registered_at": time.time()}
        return {"ok": True}

    @app.delete("/agents/{name}", dependencies=[Depends(auth)])
    def deregister(name: str):
        agents.pop(name, None)
        return {"ok": True}

    @app.get("/agents")
    def list_agents(skill: str | None = None):
        return [a for a in agents.values() if skill is None or skill in a["skills"]]

    return app
