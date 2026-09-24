"""MCP <-> agentkit bridge: kisi bhi MCP server ke tools ko agentkit `Tool` bana do.

Problem: agentkit ka Agent loop *sync* hai, MCP client *async* hai (aur connection ek
event loop mein zinda rehna chahiye). Solution: ek background thread mein event loop
chalao (anyio "blocking portal") aur sync code se usme calls bhejo.

    ┌──────── main thread (sync) ────────┐        ┌──── portal thread (async loop) ────┐
    │ Agent.run() -> tool.fn(**args) ────┼──call──► client.call_tool(name, args)       │
    │                 <── text result ───┼────────┤   (MCP session zinda rehta hai)     │
    └────────────────────────────────────┘        └─────────────────────────────────────┘

Multiple servers: har server ka alag Client; tool names ko `server__tool` se namespace
karte hain taaki do servers ke same naam wale tools (e.g. dono mein `search`) takraayein nahi.
"""
from __future__ import annotations

import json
import re
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any

from anyio.from_thread import BlockingPortal, start_blocking_portal
from mcp import Client

from agentkit import Tool

SEP = "__"
_BAD = re.compile(r"[^a-zA-Z0-9_-]")


def result_to_text(result: Any) -> str:
    """MCP CallToolResult (content blocks) -> ek string jo LLM padh sake."""
    parts = []
    for block in result.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
        elif getattr(block, "type", None) in ("image", "audio"):
            parts.append(f"[{block.type} content: {block.mime_type}, {len(block.data)} base64 chars]")
        elif getattr(block, "type", None) == "resource":
            res = block.resource
            parts.append(getattr(res, "text", None) or f"[binary resource {res.uri}]")
        else:
            parts.append(f"[{getattr(block, 'type', 'unknown')} content]")
    text = "\n".join(parts)
    if not text and result.structured_content is not None:
        text = json.dumps(result.structured_content)
    return f"ERROR: {text}" if result.is_error else text


@dataclass
class ServerHandle:
    name: str
    client: Client
    instructions: str | None
    tools: list[Any] = field(default_factory=list)  # mcp.types.Tool


class MCPBridge:
    """
    servers = {"notes": StdioServerParameters(...), "utils": "http://localhost:8000/mcp", "mem": MCPServer(...)}
    with MCPBridge(servers) as bridge:
        agent = Agent(llm, bridge.tools())
    """

    def __init__(self, servers: dict[str, Any], *, allow: set[str] | None = None, read_timeout: float = 30.0):
        self.server_specs = servers
        self.allow = allow  # optional allowlist of "server__tool" names (least privilege)
        self.read_timeout = read_timeout
        self.handles: dict[str, ServerHandle] = {}
        self._stack = ExitStack()
        self._portal: BlockingPortal | None = None

    # ---- lifecycle -------------------------------------------------------------------------------
    def __enter__(self) -> "MCPBridge":
        try:
            self._portal = self._stack.enter_context(start_blocking_portal())
            for name, spec in self.server_specs.items():
                if SEP in name or _BAD.search(name):
                    raise ValueError(f"server name {name!r} must be [a-zA-Z0-9-] and not contain '{SEP}'")
                client = self._stack.enter_context(self._portal.wrap_async_context_manager(Client(spec)))
                listed = self._portal.call(client.list_tools)
                self.handles[name] = ServerHandle(name, client, client.instructions, list(listed.tools))
        except BaseException:
            self._stack.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self._stack.close()  # sab clients band (stdio subprocesses bhi), phir portal thread

    # ---- tools -----------------------------------------------------------------------------------
    def _call(self, server: str, tool: str, arguments: dict) -> str:
        assert self._portal is not None, "use MCPBridge as a context manager"
        client = self.handles[server].client
        result = self._portal.call(lambda: client.call_tool(tool, arguments, read_timeout_seconds=self.read_timeout))
        return result_to_text(result)

    def tools(self) -> list[Tool]:
        """Har MCP tool -> agentkit Tool. MCP ka inputSchema already JSON Schema hai, seedha pass."""
        out = []
        for h in self.handles.values():
            for t in h.tools:
                full = f"{h.name}{SEP}{t.name}"
                if self.allow is not None and full not in self.allow:
                    continue
                desc = t.description or t.name
                if t.annotations and t.annotations.destructive_hint:
                    desc += " (DESTRUCTIVE)"
                out.append(Tool(
                    name=full,
                    description=f"[{h.name}] {desc}",
                    parameters=t.input_schema,
                    fn=lambda _s=h.name, _t=t.name, **kw: self._call(_s, _t, kw),
                ))
        return out

    def destructive_tools(self) -> set[str]:
        return {f"{h.name}{SEP}{t.name}" for h in self.handles.values() for t in h.tools
                if t.annotations and t.annotations.destructive_hint}

    # ---- resources & prompts (host/user-controlled, LLM tools nahi) --------------------------------
    def read_resource(self, server: str, uri: str) -> str:
        assert self._portal is not None
        client = self.handles[server].client
        res = self._portal.call(client.read_resource, uri)
        return "\n".join(getattr(c, "text", "") or f"[binary {c.uri}]" for c in res.contents)

    def list_resources(self, server: str) -> list[str]:
        assert self._portal is not None
        client = self.handles[server].client
        static = [str(r.uri) for r in self._portal.call(client.list_resources).resources]
        templates = [t.uri_template for t in self._portal.call(client.list_resource_templates).resource_templates]
        return static + templates

    def get_prompt(self, server: str, name: str, arguments: dict[str, str] | None = None) -> str:
        assert self._portal is not None
        client = self.handles[server].client
        res = self._portal.call(lambda: client.get_prompt(name, arguments or {}))
        return "\n\n".join(getattr(m.content, "text", "") for m in res.messages)

    def instructions(self) -> str:
        """Servers ki `instructions` system prompt mein daalne ke liye."""
        return "\n".join(f"- {h.name}: {h.instructions}" for h in self.handles.values() if h.instructions)
