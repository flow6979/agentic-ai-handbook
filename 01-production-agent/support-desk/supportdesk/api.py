"""HTTP API (FastAPI): agent ko ek service ki tarah expose karo.

  POST /chat   header X-User-Id  body {message, session_id?}  -> Reply JSON
  GET  /health                                                  -> liveness + model

Auth note: asli app mein user id JWT/session cookie se aata hai (gateway verify karta hai).
X-User-Id header yahan uska stand-in hai. Body mein user id KABHI trust mat karo.
"""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .service import SupportDesk


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


def create_app(desk: SupportDesk) -> FastAPI:
    app = FastAPI(title="ShopKart Support Agent", version="1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": repr(desk.llm), "read_only": desk.settings.read_only}

    @app.post("/chat")
    def chat(body: ChatIn, x_user_id: str = Header(...)) -> dict:
        # sync def => FastAPI isse threadpool mein chalata hai, event loop block nahi hota
        try:
            reply = desk.handle(x_user_id, body.message, body.session_id)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        if reply.error_code == "rate_limited":
            raise HTTPException(status_code=429, detail=reply.text)
        return reply.to_dict()

    return app
