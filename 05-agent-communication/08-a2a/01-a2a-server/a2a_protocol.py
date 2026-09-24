"""A2A (Agent2Agent) protocol ke data types + JSON-RPC helpers. From scratch, koi SDK nahi.

Spec version: A2A **v0.2.x** ke JSON-RPC shapes follow kiye hain (method names
`message/send`, `message/stream`, `tasks/get`, `tasks/cancel`; objects mein `kind`
discriminator; Agent Card `/.well-known/agent.json`). v0.3.0 ne card path
`/.well-known/agent-card.json` kar diya, isliye server dono paths serve karta hai.
Naye versions mein fields badal sakte hain; asli source: https://a2a-protocol.org

Wire pe sab camelCase hai (messageId, contextId). Python mein snake_case, alias se convert.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

PROTOCOL_VERSION = "0.2.6"


class A2AModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")

    def wire(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ Parts: message ke tukde
class TextPart(A2AModel):
    kind: Literal["text"] = "text"
    text: str


class FileContent(A2AModel):
    name: str | None = None
    mime_type: str | None = None
    bytes: str | None = None  # base64 (chhoti file)
    uri: str | None = None  # ya link (badi file)


class FilePart(A2AModel):
    kind: Literal["file"] = "file"
    file: FileContent


class DataPart(A2AModel):
    kind: Literal["data"] = "data"
    data: dict[str, Any]  # structured JSON (forms, results) -> dusra agent parse kar sake


Part = Annotated[Union[TextPart, FilePart, DataPart], Field(discriminator="kind")]


# ------------------------------------------------------------------ Message: ek turn (user ya agent)
class Message(A2AModel):
    kind: Literal["message"] = "message"
    role: Literal["user", "agent"]
    parts: list[Part]
    message_id: str = Field(default_factory=new_id)
    task_id: str | None = None
    context_id: str | None = None
    metadata: dict[str, Any] | None = None

    def text(self) -> str:
        return "\n".join(p.text for p in self.parts if isinstance(p, TextPart))

    def data(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for p in self.parts:
            if isinstance(p, DataPart):
                out.update(p.data)
        return out


def text_message(role: Literal["user", "agent"], text: str, **kw) -> Message:
    return Message(role=role, parts=[TextPart(text=text)], **kw)


# ------------------------------------------------------------------ Task: kaam ki unit, lifecycle ke saath
class TaskState(str, Enum):
    submitted = "submitted"
    working = "working"
    input_required = "input-required"
    auth_required = "auth-required"
    completed = "completed"
    canceled = "canceled"
    failed = "failed"
    rejected = "rejected"
    unknown = "unknown"


TERMINAL = {TaskState.completed, TaskState.canceled, TaskState.failed, TaskState.rejected}
INTERRUPTED = {TaskState.input_required, TaskState.auth_required}  # client ke jawab ka intezaar


class TaskStatus(A2AModel):
    state: TaskState
    message: Message | None = None
    timestamp: str = Field(default_factory=now_iso)


class Artifact(A2AModel):
    """Task ka OUTPUT (report, file, JSON). Message = baat-cheet, Artifact = deliverable."""

    artifact_id: str = Field(default_factory=new_id)
    name: str | None = None
    description: str | None = None
    parts: list[Part]


class Task(A2AModel):
    kind: Literal["task"] = "task"
    id: str = Field(default_factory=new_id)
    context_id: str = Field(default_factory=new_id)
    status: TaskStatus
    artifacts: list[Artifact] | None = None
    history: list[Message] | None = None
    metadata: dict[str, Any] | None = None


# ------------------------------------------------------------------ Streaming events
class TaskStatusUpdateEvent(A2AModel):
    kind: Literal["status-update"] = "status-update"
    task_id: str
    context_id: str
    status: TaskStatus
    final: bool = False


class TaskArtifactUpdateEvent(A2AModel):
    kind: Literal["artifact-update"] = "artifact-update"
    task_id: str
    context_id: str
    artifact: Artifact
    append: bool | None = None
    last_chunk: bool | None = None


# ------------------------------------------------------------------ Agent Card: agent ka "visiting card"
class AgentSkill(A2AModel):
    id: str
    name: str
    description: str
    tags: list[str] = []
    examples: list[str] | None = None
    input_modes: list[str] | None = None
    output_modes: list[str] | None = None


class AgentCapabilities(A2AModel):
    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = False


class AgentProvider(A2AModel):
    organization: str
    url: str | None = None


class AgentCard(A2AModel):
    protocol_version: str = PROTOCOL_VERSION
    name: str
    description: str
    url: str  # JSON-RPC endpoint
    version: str = "1.0.0"
    provider: AgentProvider | None = None
    capabilities: AgentCapabilities = AgentCapabilities()
    default_input_modes: list[str] = ["text/plain", "application/json"]
    default_output_modes: list[str] = ["text/plain", "application/json"]
    skills: list[AgentSkill] = []
    # OpenAPI-style security schemes: {"bearer": {"type": "http", "scheme": "bearer"}}
    security_schemes: dict[str, dict[str, Any]] | None = None
    security: list[dict[str, list[str]]] | None = None


# ------------------------------------------------------------------ JSON-RPC 2.0
class JSONRPCError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data

    def wire(self) -> dict[str, Any]:
        err = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


# Standard JSON-RPC codes + A2A-specific codes (-32001...)
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
TASK_NOT_FOUND, TASK_NOT_CANCELABLE, PUSH_NOT_SUPPORTED, UNSUPPORTED_OPERATION = -32001, -32002, -32003, -32004


def rpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def rpc_error(req_id: Any, err: JSONRPCError) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": err.wire()}


def parse_event(result: dict[str, Any]) -> Task | Message | TaskStatusUpdateEvent | TaskArtifactUpdateEvent:
    """`result` ke `kind` se sahi type banao (client side)."""
    kind = result.get("kind")
    model = {"task": Task, "message": Message, "status-update": TaskStatusUpdateEvent,
             "artifact-update": TaskArtifactUpdateEvent}.get(kind)
    if model is None:
        raise ValueError(f"unknown A2A result kind {kind!r}")
    return model.model_validate(result)
