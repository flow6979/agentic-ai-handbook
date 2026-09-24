"""Customer support desk: triage -> billing / tech, aur wapas triage (handback).

    triage  : sawaal samjho, sahi department ko transfer karo
    billing : invoices dekho, refund karo      (handoff: triage)
    tech    : account status dekho, password reset (handoff: triage)
"""
from __future__ import annotations

from agentkit import tool

from handoff_swarm import SwarmAgent

# Fake "database". context["customer_id"] se lookup hota hai.
INVOICES = {"C-101": [{"id": "INV-1", "amount": 499, "status": "paid"}, {"id": "INV-2", "amount": 499, "status": "paid"}]}
ACCOUNTS = {"C-101": {"plan": "Pro", "locked": True}}
REFUNDS: list[dict] = []


@tool
def list_invoices(context: dict) -> list:
    """List the current customer's invoices."""
    return INVOICES.get(context["customer_id"], [])


@tool
def refund_invoice(invoice_id: str, context: dict) -> str:
    """Refund one invoice of the current customer."""
    inv = next((i for i in INVOICES.get(context["customer_id"], []) if i["id"] == invoice_id), None)
    if inv is None:
        return f"ERROR: invoice {invoice_id} not found for this customer"
    inv["status"] = "refunded"
    REFUNDS.append({"customer": context["customer_id"], "invoice": invoice_id})
    return f"Refunded {invoice_id} ({inv['amount']})."


@tool
def account_status(context: dict) -> dict:
    """Get the current customer's account status."""
    return ACCOUNTS.get(context["customer_id"], {})


@tool
def unlock_account(context: dict) -> str:
    """Unlock the current customer's account and send a reset link."""
    ACCOUNTS[context["customer_id"]]["locked"] = False
    return "Account unlocked, reset link sent."


# `context` param JSON schema se hata do: LLM ko customer_id guess nahi karna chahiye
for _t in (list_invoices, refund_invoice, account_status, unlock_account):
    _t.parameters["properties"].pop("context", None)
    _t.parameters["required"] = [r for r in _t.parameters["required"] if r != "context"]


def build_agents() -> list[SwarmAgent]:
    return [
        SwarmAgent("triage", "Figure out what the customer needs and transfer to billing (payments, refunds, invoices) "
                   "or tech (login, account locked, bugs). Do not solve it yourself.",
                   handoffs=["billing", "tech"]),
        SwarmAgent("billing", "Handles invoices and refunds. Look up invoices before refunding. "
                   "If the issue is not about billing, transfer back to triage.",
                   tools=[list_invoices, refund_invoice], handoffs=["triage"]),
        SwarmAgent("tech", "Handles login and account problems. Check account status first. "
                   "If the issue is not technical, transfer back to triage.",
                   tools=[account_status, unlock_account], handoffs=["triage"]),
    ]
