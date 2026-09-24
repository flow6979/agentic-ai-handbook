"""Orchestrator: remote A2A agents ko discover karo, skill se chuno, kaam delegate karo.

Do tareeke:
1. `SkillRouter` (no LLM): query ke words vs card skills ke tags/examples -> best agent. Sasta, predictable.
2. `build_orchestrator_agent` (LLM): agentkit Agent jiske tools hain
       list_remote_agents()          -> sab cards ka summary
       send_to_agent(agent, message, task_id)
       ask_user(question)            -> input-required pe insaan se poochho
   LLM khud decide karta hai kisko bhejna hai, jawab kaise combine karna hai.

    user ──► Orchestrator (LLM) ──list_remote_agents──► Registry (cards)
                   │
                   ├──send_to_agent──► Travel agent (A2A)   ──► Task(input-required: "which currency?")
                   ├──ask_user──────► human: "INR"
                   └──send_to_agent(task_id)──► Travel agent ──► Task(completed + artifact)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

import httpx

from agentkit import LLM, Agent, LLMResponse, Message as AKMessage, ScriptedLLM, ToolCall, Tracer, tool

from a2a_client import A2AClient, A2AError, task_answer, task_data
from a2a_protocol import Task, TaskState

_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class RemoteAgent:
    name: str
    url: str
    client: A2AClient

    @property
    def card(self):
        return self.client.card


class AgentRegistry:
    """URLs -> cards. Real world mein yeh ek catalog service / DNS / config ho sakta hai."""

    def __init__(self, urls: list[str], *, http: dict[str, httpx.Client] | None = None, token: str | None = None):
        self.agents: dict[str, RemoteAgent] = {}
        for url in urls:
            client = A2AClient(url, http=(http or {}).get(url), token=token)
            card = client.card  # discovery: GET /.well-known/agent(-card).json
            self.agents[card.name] = RemoteAgent(card.name, url, client)

    def get(self, name: str) -> RemoteAgent:
        if name not in self.agents:
            raise KeyError(f"unknown agent {name!r}; known: {sorted(self.agents)}")
        return self.agents[name]

    def summary(self) -> list[dict]:
        return [{"name": a.name, "description": a.card.description,
                 "skills": [{"id": s.id, "description": s.description, "tags": s.tags} for s in a.card.skills],
                 "streaming": a.card.capabilities.streaming} for a in self.agents.values()]


class SkillRouter:
    """No-LLM routing: bag-of-words overlap with skill tags/name/examples."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def rank(self, query: str) -> list[tuple[float, str, str]]:
        q = set(_WORD.findall(query.lower()))
        scored = []
        for a in self.registry.agents.values():
            for s in a.card.skills:
                vocab = set(_WORD.findall(" ".join([s.name, s.description, *s.tags, *(s.examples or [])]).lower()))
                tag_hits = len(q & {t.lower() for t in s.tags})
                score = tag_hits * 2 + len(q & vocab)
                scored.append((score, a.name, s.id))
        return sorted(scored, reverse=True)

    def pick(self, query: str) -> tuple[str, str]:
        ranked = self.rank(query)
        if not ranked or ranked[0][0] == 0:
            raise LookupError(f"no agent skill matches {query!r}")
        return ranked[0][1], ranked[0][2]


def delegate(agent: RemoteAgent, text: str, *, ask_human: Callable[[str], str], max_turns: int = 3) -> Task:
    """Send + input-required loop: remote agent sawaal poochhe to insaan se jawab lekar wapas bhejo."""
    task = agent.client.send(text)
    turns = 0
    while isinstance(task, Task) and task.status.state == TaskState.input_required and turns < max_turns:
        question = task.status.message.text() if task.status.message else "More info needed"
        task = agent.client.send(ask_human(f"[{agent.name}] {question}"), task_id=task.id, context_id=task.context_id)
        turns += 1
    return task


def delegate_streaming(agent: RemoteAgent, text: str, on_event: Callable[[object], None]) -> Task | None:
    """message/stream: har status/artifact event live callback ko. Final task tasks/get se."""
    task_id = None
    for ev in agent.client.stream(text):
        on_event(ev)
        task_id = getattr(ev, "task_id", None) or getattr(ev, "id", None) or task_id
    return agent.client.get_task(task_id) if task_id else None


ORCH_SYSTEM = """You are an orchestrator. You do not answer domain questions yourself.
1. Call list_remote_agents to see which remote agents exist and their skills.
2. Call send_to_agent with the best agent and a clear self-contained message.
3. If the result state is "input-required", answer from the conversation if you can,
   otherwise call ask_user with the agent's question, then call send_to_agent again with the SAME task_id.
4. When all needed tasks are completed, give the user one combined answer and mention which agent helped."""


def build_orchestrator_agent(llm: LLM, registry: AgentRegistry, *, ask_human: Callable[[str], str],
                             tracer: Tracer | None = None) -> Agent:
    @tool
    def list_remote_agents() -> str:
        """List available remote A2A agents with their skills."""
        return json.dumps(registry.summary())

    @tool
    def send_to_agent(agent_name: str, message: str, task_id: str = "") -> str:
        """Send a message to a remote agent. Pass task_id to continue an input-required task."""
        agent = registry.get(agent_name)
        try:
            prev = agent.client.get_task(task_id) if task_id else None
            task = agent.client.send(message, task_id=task_id or None, context_id=prev.context_id if prev else None)
        except A2AError as e:
            return f"ERROR: {e}"
        if not isinstance(task, Task):  # agent ne seedha Message lautaya (task nahi)
            return json.dumps({"state": "message", "answer": task.text()})
        out = {"state": task.status.state.value, "task_id": task.id}
        if task.status.state == TaskState.input_required:
            out["question"] = task.status.message.text() if task.status.message else ""
        else:
            out["answer"] = task_answer(task)
            if data := task_data(task):
                out["data"] = data
        return json.dumps(out)

    @tool
    def ask_user(question: str) -> str:
        """Ask the human user a clarifying question and get their answer."""
        return ask_human(question)

    return Agent(llm, [list_remote_agents, send_to_agent, ask_user], ORCH_SYSTEM, name="orchestrator",
                 max_steps=10, tracer=tracer)


def offline_orchestrator_llm() -> ScriptedLLM:
    """Fake orchestrator brain: list -> send -> (ask_user -> send again) -> final."""

    def brain(messages: list[AKMessage], tools) -> LLMResponse | str:
        user_q = next(m.content for m in messages if m.role == "user")
        tool_msgs = [m for m in messages if m.role == "tool"]
        if not tool_msgs:
            return LLMResponse(None, [ToolCall("o1", "list_remote_agents", {})])
        last = tool_msgs[-1]
        if last.name == "list_remote_agents":
            agents = json.loads(last.content)
            words = set(_WORD.findall(user_q.lower()))
            best = max(agents, key=lambda a: sum(len(words & set(t.lower() for t in s["tags"])) for s in a["skills"]))
            return LLMResponse(None, [ToolCall("o2", "send_to_agent", {"agent_name": best["name"], "message": user_q})])
        if last.name == "send_to_agent":
            res = json.loads(last.content) if not last.content.startswith("ERROR") else {"state": "failed", "answer": last.content}
            if res["state"] == "input-required":
                return LLMResponse(None, [ToolCall("o3", "ask_user", {"question": res["question"]})])
            agent = next(json.loads(m.content) for m in tool_msgs if m.name == "list_remote_agents")
            return f"Answer (via remote agent, {len(agent)} agent(s) discovered): {res.get('answer')}"
        if last.name == "ask_user":
            sends = [m for m in messages if m.role == "assistant" and m.tool_calls
                     and m.tool_calls[0].name == "send_to_agent"]
            prev_call = sends[-1].tool_calls[0].arguments
            task_id = json.loads([m for m in tool_msgs if m.name == "send_to_agent"][-1].content)["task_id"]
            return LLMResponse(None, [ToolCall("o4", "send_to_agent", {"agent_name": prev_call["agent_name"],
                                                                        "message": last.content, "task_id": task_id})])
        return "I could not complete the request."

    return ScriptedLLM(brain)
