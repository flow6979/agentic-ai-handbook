"""Swarm with handoffs (OpenAI Swarm / Agents SDK style, from scratch).

Koi central boss nahi. Jo agent 'active' hai wahi user se baat karta hai; agar kaam uske
bas ka nahi to woh `transfer_to_<peer>` tool call karke control peer ko de deta hai.

    user ──► [triage] ──transfer_to_refunds──► [refunds] ──issue_refund──► done
                 │                                 │
                 └──transfer_to_orders──► [orders] ┘ (peer-to-peer, koi supervisor nahi)

Shared state:
  - messages  : poori conversation sab agents ke saath travel karti hai (continuity)
  - context   : context variables (customer_id, order_id...) jo tools padhte/likhte hain

Supervisor (project 03) se farq: wahan har step pe manager decide karta hai (extra LLM call,
central control). Yahan decision distributed hai -> kam calls, lekin loop/ping-pong ka risk,
isliye max_handoffs guard zaroori hai.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from agentkit import LLM, Message, ScriptedLLM, Tool, Tracer, Usage, call, get_llm, tool_response

HANDOFF_PREFIX = "transfer_to_"


def llm_for(role: str) -> LLM:
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


@dataclass
class SwarmAgent:
    name: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)  # kin peers ko transfer kar sakta hai

    def all_tools(self) -> list[Tool]:
        """Har allowed peer ke liye ek auto-generated handoff tool."""
        hand = [
            Tool(name=f"{HANDOFF_PREFIX}{peer}", description=f"Hand the conversation over to the {peer} agent.",
                 parameters={"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
                 fn=lambda reason="", _peer=peer: f"HANDOFF -> {_peer}")
            for peer in self.handoffs
        ]
        return self.tools + hand


@dataclass
class SwarmResult:
    reply: str
    active_agent: str
    path: list[str]  # kaun kaun se agents se guzra
    messages: list[Message]
    context: dict[str, Any]
    usage: Usage
    stopped_reason: str = "reply"  # reply | max_handoffs | max_steps


class Swarm:
    def __init__(self, agents: list[SwarmAgent], llm_factory: Callable[[str], LLM] = llm_for,
                 max_handoffs: int = 4, max_steps: int = 12, verbose: bool | None = None):
        self.agents = {a.name: a for a in agents}
        self.llms = {a.name: llm_factory(a.name) for a in agents}  # har peer apna model use kar sakta hai
        self.max_handoffs, self.max_steps = max_handoffs, max_steps
        self.tracer = Tracer(name="swarm", verbose=verbose)

    def run(self, user_input: str, start: str, context: dict[str, Any] | None = None,
            history: list[Message] | None = None) -> SwarmResult:
        context = context if context is not None else {}
        messages = [*(history or []), Message.user(user_input)]
        active, path, handoffs, usage = start, [start], 0, Usage()

        for _ in range(self.max_steps):
            agent = self.agents[active]
            tools = {t.name: t for t in agent.all_tools()}
            # Context variables system prompt mein inject -> agent ko pata hai kiske saath baat ho rahi
            system = f"ROLE: {agent.name}\n{agent.instructions}\nCONTEXT: {context}"
            resp = self.llms[active].chat([Message.system(system), *messages], [t.spec for t in tools.values()] or None)
            usage = usage + resp.usage
            messages.append(Message.assistant(resp.content, resp.tool_calls or None))
            if not resp.tool_calls:
                return SwarmResult(resp.content or "", active, path, messages, context, usage)

            for c in resp.tool_calls:
                if c.name.startswith(HANDOFF_PREFIX):
                    target = c.name[len(HANDOFF_PREFIX):]
                    if target not in agent.handoffs or target not in self.agents:
                        messages.append(Message.tool(c, f"ERROR: cannot hand off to {target!r}"))
                        continue
                    handoffs += 1
                    self.tracer.event("tool", f"{active} -> {target} ({c.arguments.get('reason', '')})")
                    messages.append(Message.tool(c, f"Transferred to {target}. {target} now handles the user."))
                    active = target
                    path.append(target)
                    if handoffs > self.max_handoffs:  # ping-pong guard
                        return SwarmResult("Sorry, let me connect you to a human agent.", active, path, messages,
                                           context, usage, "max_handoffs")
                    break  # baaki tool calls purane agent ke the; naya agent fresh decide karega
                tool = tools.get(c.name)
                try:
                    result = tool.run({**c.arguments, "context": context}) if tool else f"ERROR: unknown tool {c.name}"
                except Exception as e:
                    result = f"ERROR: {e}"
                self.tracer.event("tool", f"[{active}] {c.name}({c.arguments}) -> {result}")
                messages.append(Message.tool(c, result))
        return SwarmResult("I could not finish.", active, path, messages, context, usage, "max_steps")


# --------------------------------------------------------------------------- customer-service peers
ORDERS = {"A100": {"item": "headphones", "status": "delivered", "amount": 2999, "customer": "C1"},
          "A200": {"item": "router", "status": "shipped", "amount": 4499, "customer": "C1"}}


def _ctx_tool(name: str, description: str, props: dict, fn) -> Tool:
    """Tool jiske function ko shared `context` dict bhi milta hai (LLM ko yeh param dikhta nahi)."""
    return Tool(name, description, {"type": "object", "properties": props, "required": list(props)}, fn)


def lookup_order(order_id: str, context: dict) -> str:
    order = ORDERS.get(order_id)
    if not order:
        return f"No order {order_id}"
    context["order_id"] = order_id  # context variable set -> baaki agents ko bhi dikhega
    return f"{order_id}: {order['item']}, status={order['status']}, amount=INR {order['amount']}"


def issue_refund(order_id: str, reason: str, context: dict) -> str:
    order = ORDERS.get(order_id)
    if not order:
        return f"No order {order_id}"
    if order["status"] != "delivered":
        return f"Cannot refund {order_id}: status is {order['status']}"
    context.setdefault("refunds", []).append(order_id)
    return f"Refund of INR {order['amount']} issued for {order_id} ({reason})"


def troubleshoot(device: str, context: dict) -> str:
    return f"For {device}: 1) power-cycle 2) update firmware 3) factory reset if still failing."


def build_support_swarm() -> list[SwarmAgent]:
    s = {"type": "string"}
    return [
        SwarmAgent("triage", "Greet the user, figure out what they need and transfer to the right specialist. Do not solve issues yourself.",
                   handoffs=["orders", "refunds", "tech"]),
        SwarmAgent("orders", "Answer order status questions using lookup_order. For refunds, transfer to refunds.",
                   [_ctx_tool("lookup_order", "Look up an order by id", {"order_id": s}, lookup_order)],
                   handoffs=["refunds", "triage"]),
        SwarmAgent("refunds", "Process refunds with issue_refund. Only delivered orders can be refunded.",
                   [_ctx_tool("issue_refund", "Refund an order", {"order_id": s, "reason": s}, issue_refund)],
                   handoffs=["triage"]),
        SwarmAgent("tech", "Help with device problems using troubleshoot.",
                   [_ctx_tool("troubleshoot", "Troubleshooting steps for a device", {"device": s}, troubleshoot)],
                   handoffs=["triage"]),
    ]


# --------------------------------------------------------------------------- offline fake
def offline_llm() -> ScriptedLLM:
    """Keyword-based fake: triage routes, specialists call their tool then answer."""

    def respond(messages, tools):
        system = messages[0].content
        role = system.splitlines()[0].replace("ROLE: ", "")
        user = next(m.content for m in reversed(messages) if m.role == "user").lower()
        last = messages[-1]
        if role == "triage":
            if last.role == "tool" and not last.content.startswith("Transferred"):  # handoff failed etc.
                return "Could you tell me more?"
            if "refund" in user:
                return tool_response(call("transfer_to_refunds", reason="refund request"))
            if "where" in user or "status" in user:
                return tool_response(call("transfer_to_orders", reason="order status"))
            if "not working" in user or "wifi" in user:
                return tool_response(call("transfer_to_tech", reason="device issue"))
            return "Hi! Do you need help with an order, a refund or a device?"
        if last.role == "tool" and not last.content.startswith("Transferred"):
            return f"Done: {last.content}"
        # Specialist ko off-topic message mila -> wapas triage (ya seedha sahi peer) ko do
        domain = {"orders": ("where", "status"), "refunds": ("refund",), "tech": ("not working", "wifi")}
        if last.role == "user" and not any(k in user for k in domain.get(role, ())):
            if role == "orders" and "refund" in user:
                return tool_response(call("transfer_to_refunds", reason="refund request"))
            return tool_response(call("transfer_to_triage", reason="off-topic for me"))
        if role == "orders":
            return tool_response(call("lookup_order", order_id="A200"))
        if role == "refunds":
            return tool_response(call("issue_refund", order_id="A100", reason="customer request"))
        if role == "tech":
            return tool_response(call("troubleshoot", device="router"))
        return "?"

    return ScriptedLLM(respond)
