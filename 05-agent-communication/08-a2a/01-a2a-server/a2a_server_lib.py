"""Generic A2A server: koi bhi 'executor' (tumhara agent logic) do, yeh use A2A endpoint bana deta hai.

    app = build_a2a_app(card, executor)      # FastAPI app
    uvicorn.run(app, port=9001)

Executor = async generator jo events yield karta hai:

    async def executor(ctx: RequestContext):
        yield ctx.status("working", "thinking...")
        yield ctx.artifact([TextPart(text="answer")], name="answer")
        yield ctx.status("completed", "done", final=True)

Server ka kaam (protocol plumbing), executor ka kaam (agent ki intelligence) - alag alag.
Official a2a-sdk mein yahi split hai: AgentExecutor + EventQueue + DefaultRequestHandler + TaskStore.

Flow (message/send):
    client ──message──► server: task banao / purana task (input-required) uthao
                        executor chalao, har event se task update karo
                        ruk jao jab state terminal (completed/failed/...) ya input-required ho
    client ◄──Task───── server (status + artifacts + history)
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from a2a_protocol import (INTERRUPTED, INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST, METHOD_NOT_FOUND, PARSE_ERROR,
                          PUSH_NOT_SUPPORTED, TASK_NOT_CANCELABLE, TASK_NOT_FOUND, TERMINAL, UNSUPPORTED_OPERATION,
                          AgentCard, Artifact, DataPart, JSONRPCError, Message, Part, Task, TaskArtifactUpdateEvent, TaskState,
                          TaskStatus, TaskStatusUpdateEvent, new_id, rpc_error, rpc_result, text_message)

log = logging.getLogger("a2a.server")
Event = TaskStatusUpdateEvent | TaskArtifactUpdateEvent


@dataclass
class RequestContext:
    task: Task
    message: Message  # latest incoming user message
    configuration: dict[str, Any] = field(default_factory=dict)

    @property
    def history(self) -> list[Message]:
        return self.task.history or []

    def status(self, state: str | TaskState, text: str | None = None, *, final: bool = False,
               data: dict | None = None) -> TaskStatusUpdateEvent:
        msg = None
        if text is not None or data is not None:
            msg = text_message("agent", text or "", task_id=self.task.id, context_id=self.task.context_id,
                               metadata={"state": TaskState(state).value})  # kis state ka message tha
            if data is not None:
                msg.parts.append(DataPart(data=data))
        return TaskStatusUpdateEvent(task_id=self.task.id, context_id=self.task.context_id,
                                     status=TaskStatus(state=TaskState(state), message=msg), final=final)

    def artifact(self, parts: list[Part], name: str | None = None, **kw) -> TaskArtifactUpdateEvent:
        return TaskArtifactUpdateEvent(task_id=self.task.id, context_id=self.task.context_id,
                                       artifact=Artifact(parts=parts, name=name, **kw), last_chunk=True)


Executor = Callable[[RequestContext], AsyncIterator[Event]]


class TaskStore:
    """In-memory. Production mein Redis/DB (restart ke baad bhi task yaad rahe, multiple replicas share karein)."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.running: dict[str, asyncio.Task] = {}

    def get(self, task_id: str) -> Task:
        if task_id not in self.tasks:
            raise JSONRPCError(TASK_NOT_FOUND, f"Task {task_id} not found")
        return self.tasks[task_id]


def _apply(task: Task, ev: Event) -> None:
    """Event ko stored task pe laagu karo (state machine yahi hai)."""
    if isinstance(ev, TaskStatusUpdateEvent):
        task.status = ev.status
        if ev.status.message:
            task.history = (task.history or []) + [ev.status.message]
    else:
        arts = task.artifacts or []
        existing = next((a for a in arts if a.artifact_id == ev.artifact.artifact_id), None)
        if existing and ev.append:
            existing.parts.extend(ev.artifact.parts)
        else:
            arts.append(ev.artifact)
        task.artifacts = arts


def _trim(task: Task, history_length: int | None) -> dict[str, Any]:
    out = task.wire()
    if history_length is not None and "history" in out:
        out["history"] = out["history"][-history_length:] if history_length > 0 else []
    return out


def build_a2a_app(card: AgentCard, executor: Executor, *, token: str | None = None,
                  store: TaskStore | None = None) -> FastAPI:
    app = FastAPI(title=card.name)
    store = store or TaskStore()
    app.state.store = store

    # ------------------------------------------------------------ discovery
    @app.get("/.well-known/agent.json")  # v0.2.x path
    @app.get("/.well-known/agent-card.json")  # v0.3+ path
    async def agent_card() -> dict:
        return card.wire()

    # ------------------------------------------------------------ helpers
    def _check_auth(request: Request) -> None:
        if token is None:
            return
        got = request.headers.get("authorization", "")
        if not (got.startswith("Bearer ") and hmac.compare_digest(got[7:], token)):
            raise PermissionError

    def _start_or_resume(params: dict) -> tuple[Task, RequestContext]:
        try:
            message = Message.model_validate(params["message"])
        except (KeyError, ValidationError) as e:
            raise JSONRPCError(INVALID_PARAMS, f"invalid message: {e}") from e
        if message.role != "user":
            raise JSONRPCError(INVALID_PARAMS, "incoming message role must be 'user'")
        if message.task_id:  # multi-turn: purane task ko aage badhao
            task = store.get(message.task_id)
            if task.status.state in TERMINAL:
                raise JSONRPCError(UNSUPPORTED_OPERATION, f"task is {task.status.state.value}; start a new task")
            if task.status.state not in INTERRUPTED:
                raise JSONRPCError(UNSUPPORTED_OPERATION, "task is still running")
        else:
            task = Task(status=TaskStatus(state=TaskState.submitted), history=[],
                        context_id=message.context_id or new_id())
            store.tasks[task.id] = task
        message.task_id, message.context_id = task.id, task.context_id
        task.history = (task.history or []) + [message]
        return task, RequestContext(task, message, params.get("configuration") or {})

    async def _drive(task: Task, ctx: RequestContext, on_event: Callable[[Event], Awaitable[None]] | None = None):
        """Executor chalao jab tak final/terminal/input-required na aa jaye."""
        try:
            async for ev in executor(ctx):
                if task.status.state == TaskState.canceled:  # beech mein cancel ho gaya
                    return
                _apply(task, ev)
                if on_event:
                    await on_event(ev)
                if (isinstance(ev, TaskStatusUpdateEvent) and ev.final) or task.status.state in TERMINAL | INTERRUPTED:
                    return
            if task.status.state not in TERMINAL | INTERRUPTED:  # executor bina final ke khatam ho gaya
                ev = ctx.status(TaskState.completed, final=True)
                _apply(task, ev)
                if on_event:
                    await on_event(ev)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # agent crash -> task failed (server crash nahi)
            log.exception("executor failed")
            ev = ctx.status(TaskState.failed, f"agent error: {type(e).__name__}: {e}", final=True)
            _apply(task, ev)
            if on_event:
                await on_event(ev)

    # ------------------------------------------------------------ JSON-RPC endpoint
    @app.post("/")
    async def rpc(request: Request):
        try:
            _check_auth(request)
        except PermissionError:
            return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            body = json.loads(await request.body())
        except json.JSONDecodeError:
            return JSONResponse(rpc_error(None, JSONRPCError(PARSE_ERROR, "Parse error")))
        req_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
            return JSONResponse(rpc_error(req_id, JSONRPCError(INVALID_REQUEST, "Invalid Request")))
        method, params = body["method"], body.get("params") or {}
        try:
            if method == "message/send":
                task, ctx = _start_or_resume(params)
                if ctx.configuration.get("blocking", True):
                    await _drive(task, ctx)
                else:  # async: turant task lautao, kaam background mein; client tasks/get se poll kare
                    task.status = TaskStatus(state=TaskState.working)
                    store.running[task.id] = asyncio.create_task(_drive(task, ctx))
                return JSONResponse(rpc_result(req_id, _trim(task, ctx.configuration.get("historyLength"))))

            if method == "message/stream":
                if not card.capabilities.streaming:
                    raise JSONRPCError(UNSUPPORTED_OPERATION, "streaming not supported by this agent")
                task, ctx = _start_or_resume(params)
                return StreamingResponse(_sse(req_id, task, ctx), media_type="text/event-stream")

            if method == "tasks/get":
                task = store.get(params.get("id", ""))
                return JSONResponse(rpc_result(req_id, _trim(task, params.get("historyLength"))))

            if method == "tasks/cancel":
                task = store.get(params.get("id", ""))
                if task.status.state in TERMINAL:
                    raise JSONRPCError(TASK_NOT_CANCELABLE, f"task already {task.status.state.value}")
                task.status = TaskStatus(state=TaskState.canceled)
                if (running := store.running.pop(task.id, None)) is not None:
                    running.cancel()
                return JSONResponse(rpc_result(req_id, task.wire()))

            if method.startswith("tasks/pushNotificationConfig/"):
                raise JSONRPCError(PUSH_NOT_SUPPORTED, "push notifications not supported")
            raise JSONRPCError(METHOD_NOT_FOUND, f"Method not found: {method}")
        except JSONRPCError as e:
            return JSONResponse(rpc_error(req_id, e))
        except Exception as e:  # pragma: no cover - last resort
            log.exception("rpc failed")
            return JSONResponse(rpc_error(req_id, JSONRPCError(INTERNAL_ERROR, str(e))))

    async def _sse(req_id: Any, task: Task, ctx: RequestContext):
        """Server-Sent Events: har event `data: <json-rpc response>\\n\\n`."""
        queue: asyncio.Queue = asyncio.Queue()

        async def push(ev: Event) -> None:
            await queue.put(ev)

        def frame(result: dict) -> str:
            return f"data: {json.dumps(rpc_result(req_id, result))}\n\n"

        yield frame(task.wire())  # pehla event: task ban gaya (submitted)
        runner = asyncio.create_task(_drive(task, ctx, push))
        store.running[task.id] = runner
        try:
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, runner}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    ev = getter.result()
                    yield frame(ev.wire())
                    if isinstance(ev, TaskStatusUpdateEvent) and (ev.final or ev.status.state in TERMINAL | INTERRUPTED):
                        break
                else:
                    getter.cancel()
                    while not queue.empty():
                        yield frame(queue.get_nowait().wire())
                    break
        finally:
            store.running.pop(task.id, None)

    return app
