"""LLM-agnostic MCP host: agentkit Agent + MCPBridge.

Yeh wahi kaam karta hai jo Claude Desktop / Cursor karte hain (MCP *host*):
servers connect karo, unke tools LLM ko do, LLM ke tool calls servers tak pahunchao.
Farak itna hai ki LLM koi bhi ho sakta hai (get_llm se: Groq, Gemini, OpenAI, Ollama...).
"""
from __future__ import annotations

import os
import sys
from typing import Callable

from mcp import StdioServerParameters

from agentkit import LLM, Agent, LLMResponse, Message, ScriptedLLM, ToolCall, Tracer

from mcp_bridge import MCPBridge

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES_SERVER = os.path.join(HERE, "..", "01-mcp-server-stdio", "mcp_notes_server.py")
UTILS_SERVER = os.path.join(HERE, "mcp_utils_server.py")

SYSTEM = """You are a personal assistant connected to MCP servers.
Tool names look like <server>__<tool>. Use tools to act; never invent note ids.
Server notes:
{instructions}"""


def default_servers(notes_db: str) -> dict:
    """Do stdio servers: notes (01 wala) + utils. Host inhe subprocess ki tarah launch karta hai."""
    return {
        "notes": StdioServerParameters(command=sys.executable, args=[NOTES_SERVER], env={"NOTES_DB": notes_db}),
        "utils": StdioServerParameters(command=sys.executable, args=[UTILS_SERVER]),
    }


def confirm_destructive(bridge: MCPBridge, ask: Callable[[str], str] = input) -> Callable[[str, dict], bool]:
    """Human-in-the-loop: destructive tools (annotation se pata chalta hai) se pehle user se poochho."""
    risky = bridge.destructive_tools()

    def approve(name: str, args: dict) -> bool:
        if name not in risky:
            return True
        return ask(f"Allow {name}({args})? [y/N] ").strip().lower() == "y"

    return approve


def build_agent(llm: LLM, bridge: MCPBridge, *, approve=None, tracer: Tracer | None = None) -> Agent:
    return Agent(
        llm,
        bridge.tools(),
        SYSTEM.format(instructions=bridge.instructions() or "(none)"),
        name="mcp-host",
        max_steps=8,
        approve=approve,
        tracer=tracer,
    )


def offline_llm() -> ScriptedLLM:
    """Bina API key ke demo: ek chhota 'fake brain' jo user ki baat dekh ke tools call karta hai."""

    def brain(messages: list[Message], tools) -> LLMResponse | str:
        last = messages[-1]
        names = {t.name for t in (tools or [])}
        if last.role == "tool":
            done_tools = [m.name for m in messages if m.role == "tool"]
            if "notes__add_note" in done_tools and "notes__search_notes" not in done_tools and "notes__search_notes" in names:
                return LLMResponse(None, [ToolCall("c2", "notes__search_notes", {"query": "groceries"})])
            results = "\n".join(f"- {m.name}: {m.content}" for m in messages if m.role == "tool")
            return f"Done. Here is what the tools returned:\n{results}"
        text = (last.content or "").lower()
        if "calculate" in text or "*" in text:
            return LLMResponse(None, [ToolCall("c1", "utils__calculate", {"expression": "(12.5*4)+3"})])
        if "delete" in text:
            return LLMResponse(None, [ToolCall("c1", "notes__delete_note", {"note_id": 1})])
        return LLMResponse(None, [ToolCall("c1", "notes__add_note",
                                           {"title": "Groceries", "body": "milk, eggs, bread", "tags": ["groceries"]})])

    return ScriptedLLM(brain)
