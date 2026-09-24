"""Currency + travel expert: andar agentkit Agent (koi bhi LLM), bahar A2A protocol.

Bahar wale ko sirf Agent Card aur JSON-RPC dikhta hai. Andar kaunsa LLM, kaunse tools,
kaunsa framework - yeh sab 'opaque' hai. Yahi A2A ka core idea hai.

Special conventions:
- Agent ko info kam lage to woh `NEED_INPUT: <sawaal>` bolta hai -> hum task ko
  `input-required` state mein daal dete hain; client usi taskId pe jawab bhejta hai.
- Tool calls ko streaming "working" updates mein badal dete hain (Tracer hook se).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from agentkit import LLM, Agent, LLMResponse, Message as AKMessage, ScriptedLLM, ToolCall, Tracer, tool

from a2a_protocol import (AgentCapabilities, AgentCard, AgentProvider, AgentSkill, DataPart, TaskState, TextPart)
from a2a_server_lib import RequestContext, build_a2a_app

# 1 USD = X (offline table; --live-rates se frankfurter.app se asli rates)
USD_RATES = {"USD": 1.0, "EUR": 0.92, "INR": 83.0, "GBP": 0.79, "JPY": 150.0, "AED": 3.67, "SGD": 1.35}

TIPS = {
    "paris": "Buy a Navigo weekly pass for metro; most museums are free on the first Sunday; tipping is optional.",
    "tokyo": "Get a Suica/PASMO card; carry some cash; trains stop around midnight; no tipping.",
    "goa": "Rent a scooter with a valid licence; November-February is the best season; carry cash for shacks.",
    "london": "Use contactless for the Tube (daily cap applies); museums are mostly free; carry an umbrella.",
    "dubai": "Metro has a women-only carriage; dress modestly in malls; summer is extremely hot (Jun-Sep).",
}

SYSTEM = """You are a currency and travel expert agent.
Use convert_currency for any money conversion and travel_tips for destination advice.
If the user asks to convert but does NOT say the target currency (or amount), reply with exactly:
NEED_INPUT: <one short question>
Otherwise answer concisely."""


def make_tools(live_rates: bool, conversions: list[dict]):
    """Tools per-request banate hain taaki is request ke conversions DataPart mein bhej sakein."""

    def rate(frm: str, to: str) -> float:
        if live_rates:
            r = httpx.get("https://api.frankfurter.app/latest", params={"from": frm, "to": to}, timeout=10)
            r.raise_for_status()
            return r.json()["rates"][to]
        if frm not in USD_RATES or to not in USD_RATES:
            raise ValueError(f"unsupported currency; known: {sorted(USD_RATES)}")
        return USD_RATES[to] / USD_RATES[frm]

    @tool
    def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
        """Convert money between currencies (ISO codes like USD, EUR, INR)."""
        frm, to = from_currency.upper(), to_currency.upper()
        r = rate(frm, to)
        result = {"amount": amount, "from": frm, "to": to, "rate": round(r, 6), "converted": round(amount * r, 2)}
        conversions.append(result)
        return json.dumps(result)

    @tool
    def travel_tips(city: str) -> str:
        """Practical travel tips for a city."""
        return TIPS.get(city.lower().strip(), f"No curated tips for {city}; general advice: check visa and local SIM options.")

    return [convert_currency, travel_tips]


class QueueTracer(Tracer):
    """agentkit Tracer -> asyncio queue. Agent thread mein chalta hai, isliye call_soon_threadsafe."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        super().__init__(verbose=False, name="travel-agent")
        self.loop, self.queue = loop, queue

    def event(self, kind: str, message: str, **data: Any) -> None:
        super().event(kind, message, **data)
        if kind == "tool":
            self.loop.call_soon_threadsafe(self.queue.put_nowait, f"calling {message}")


def _to_agentkit_history(ctx: RequestContext) -> list[AKMessage]:
    """A2A history (user/agent) -> agentkit messages.

    - latest user message chhod do (woh run() mein alag jaata hai)
    - agent ke 'working...' progress notes chhod do (noise); sirf asli jawab/sawaal rakho
    """
    out = []
    for m in ctx.history:
        if m.message_id == ctx.message.message_id or not m.text():
            continue
        if m.role == "agent" and (m.metadata or {}).get("state") == "working":
            continue
        out.append(AKMessage.user(m.text()) if m.role == "user" else AKMessage.assistant(m.text()))
    return out


def make_executor(llm: LLM, *, live_rates: bool = False):
    async def executor(ctx: RequestContext):
        yield ctx.status(TaskState.working, "Travel expert is working on it")
        loop, queue = asyncio.get_running_loop(), asyncio.Queue()
        conversions: list[dict] = []
        agent = Agent(llm, make_tools(live_rates, conversions), SYSTEM, name="travel-agent", max_steps=6,
                      tracer=QueueTracer(loop, queue))
        user_input = ctx.message.text()
        if ctx.message.data():  # structured DataPart bhi aa sakta hai
            user_input += "\nStructured input: " + json.dumps(ctx.message.data())
        job = asyncio.create_task(asyncio.to_thread(agent.run, user_input, _to_agentkit_history(ctx)))
        while not job.done() or not queue.empty():  # tool calls ko live stream karo
            try:
                note = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield ctx.status(TaskState.working, note)
            except asyncio.TimeoutError:
                continue
        result = job.result()

        if result.output.strip().startswith("NEED_INPUT:"):
            question = result.output.split("NEED_INPUT:", 1)[1].strip()
            yield ctx.status(TaskState.input_required, question, final=True)
            return
        parts: list = [TextPart(text=result.output)]
        if conversions:
            parts.append(DataPart(data={"conversions": conversions}))
        yield ctx.artifact(parts, name="travel-answer", description="Answer from the travel expert")
        yield ctx.status(TaskState.completed, "Done", final=True)

    return executor


def make_card(url: str) -> AgentCard:
    return AgentCard(
        name="Travel & Currency Expert",
        description="Converts currencies and gives practical travel tips for popular destinations.",
        url=url,
        provider=AgentProvider(organization="agentic-ai-handbook"),
        capabilities=AgentCapabilities(streaming=True, state_transition_history=True),
        skills=[
            AgentSkill(id="currency-conversion", name="Currency conversion",
                       description="Convert an amount between currencies using current rates.",
                       tags=["currency", "money", "exchange", "forex"], examples=["Convert 100 USD to INR"]),
            AgentSkill(id="travel-tips", name="Travel tips",
                       description="Practical tips for a destination city.",
                       tags=["travel", "tips", "city", "trip"], examples=["Tips for Tokyo"]),
        ],
    )


def create_app(llm: LLM, url: str = "http://127.0.0.1:9001/", *, live_rates: bool = False, token: str | None = None):
    card = make_card(url)
    if token:
        card.security_schemes = {"bearer": {"type": "http", "scheme": "bearer"}}
        card.security = [{"bearer": []}]
    return build_a2a_app(card, make_executor(llm, live_rates=live_rates), token=token)


# ----------------------------------------------------------------- offline "brain" (no API key)
_CODES = re.compile(r"\b(" + "|".join(USD_RATES) + r")\b", re.I)
_AMOUNT = re.compile(r"\b(\d+(?:\.\d+)?)\b")


def offline_llm() -> ScriptedLLM:
    def brain(messages: list[AKMessage], tools) -> LLMResponse | str:
        last = messages[-1]
        if last.role == "tool":
            if last.name == "convert_currency":
                d = json.loads(last.content or "{}")
                return f"{d['amount']} {d['from']} = {d['converted']} {d['to']} (rate {d['rate']})."
            return f"Tips: {last.content}"
        user_text = " ".join(m.content or "" for m in messages if m.role == "user")
        codes = list(dict.fromkeys(c.upper() for c in _CODES.findall(user_text)))  # unique, order preserved
        amount = _AMOUNT.search(user_text)
        if "convert" in user_text.lower() or (amount and codes):
            if not amount:
                return "NEED_INPUT: How much money should I convert?"
            if len(codes) < 2:
                return f"NEED_INPUT: Which currency should I convert {amount.group(1)} {codes[0] if codes else ''} to?".replace("  ", " ")
            return LLMResponse(None, [ToolCall("c1", "convert_currency",
                                               {"amount": float(amount.group(1)), "from_currency": codes[0],
                                                "to_currency": codes[1]})])
        for city in TIPS:
            if city in user_text.lower():
                return LLMResponse(None, [ToolCall("c1", "travel_tips", {"city": city})])
        return "I can convert currencies (e.g. 'convert 100 USD to INR') and give travel tips (e.g. 'tips for Tokyo')."

    return ScriptedLLM(brain)
