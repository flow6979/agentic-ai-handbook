"""Same task, do tareeke: fixed WORKFLOW (code decides steps) vs AGENT (LLM decides steps).

Task: "Customer ke cart ka total (tax ke saath) batao aur ek friendly message likho."

WORKFLOW: code pehle se jaanta hai ki steps kya hain -> get_cart -> compute_total -> LLM se message.
          LLM sirf ek jagah use hota hai (message likhne ke liye). Predictable, sasta, testable.

AGENT:    LLM ko tools de do, woh khud decide karega kaunsa tool kab chalana hai.
          Flexible (naye sawaal bhi handle kar lega), lekin kam predictable aur zyada LLM calls.
"""
from __future__ import annotations

from dataclasses import dataclass

from agentkit import LLM, Agent, NullTracer, ScriptedLLM, Tracer, call, tool, tool_response

# ---- Fake "database" + tools (dono approaches same tools use karte hain) -------------

CARTS = {
    "u1": [{"item": "Keyboard", "price": 2499.0, "qty": 1}, {"item": "Mouse", "price": 799.0, "qty": 2}],
    "u2": [{"item": "Monitor", "price": 12999.0, "qty": 1}],
}
TAX_RATE = 0.18


@tool
def get_cart(user_id: str) -> list:
    """Return the cart items (item, price, qty) for a user id."""
    if user_id not in CARTS:
        raise KeyError(f"no cart for user {user_id}")
    return CARTS[user_id]


@tool
def compute_total(subtotal: float, tax_rate: float = TAX_RATE) -> dict:
    """Compute tax and grand total for a subtotal."""
    tax = round(subtotal * tax_rate, 2)
    return {"subtotal": round(subtotal, 2), "tax": tax, "total": round(subtotal + tax, 2)}


# ---- Approach 1: WORKFLOW (fixed chain) -------------------------------------------------


@dataclass
class ChainOutput:
    total: dict
    message: str
    llm_calls: int


def run_as_chain(llm: LLM, user_id: str) -> ChainOutput:
    items = get_cart.fn(user_id)  # step 1: code calls the tool directly (no LLM decision)
    subtotal = sum(i["price"] * i["qty"] for i in items)
    total = compute_total.fn(subtotal)  # step 2: deterministic math in code
    # step 3: sirf yahan LLM, aur uska kaam narrow hai
    message = llm.complete(
        f"Items: {items}\nTotals (INR): {total}\nWrite a 2-line friendly cart summary for the customer.",
        system="You write short, friendly e-commerce messages. Use the numbers exactly as given.",
    )
    return ChainOutput(total, message, llm_calls=1)


# ---- Approach 2: AGENT (LLM decides) ----------------------------------------------------


def run_as_agent(llm: LLM, question: str, tracer: Tracer | None = None):
    agent = Agent(
        llm,
        [get_cart, compute_total],
        system_prompt=(
            "You are a shopping assistant. Use tools to look up carts and compute totals. "
            "Never do tax math yourself; call compute_total. Answer in 2 friendly lines."
        ),
        name="cart-agent",
        max_steps=6,
        tracer=tracer or NullTracer(),
    )
    return agent.run(question)


# ---- Offline demo LLMs (koi API key nahi chahiye) -----------------------------------------


def offline_chain_llm() -> ScriptedLLM:
    return ScriptedLLM(["Aapke cart mein Keyboard aur 2 Mouse hain.\nTax ke saath total: INR 4834.46. Happy shopping!"])


def offline_agent_llm() -> ScriptedLLM:
    return ScriptedLLM([
        tool_response(call("get_cart", user_id="u1"), text="I need the cart first."),
        tool_response(call("compute_total", subtotal=4097.0)),
        "Aapke cart mein Keyboard aur 2 Mouse hain.\nTax ke saath total: INR 4834.46. Happy shopping!",
    ])
