"""Agent ke tools. Har request pe naye bante hain, current customer se 'bound' hote hain.

Security pattern: customer_id LLM se argument ke roop mein NAHI aata. Woh closure mein
fixed hai (authenticated user). Warna prompt injection se 'cust_2 ka order dikhao' ho jaata.
"""
from __future__ import annotations

from agentkit import Tool, tool

from .policy import TOOL_TIERS, ApprovalPolicy, Tier
from .store import Store


def build_tools(store: Store, customer_id: str, policy: ApprovalPolicy, max_tier: Tier = Tier.WRITE) -> list[Tool]:
    @tool
    def lookup_order(order_id: str) -> dict:
        """Look up one of the current customer's orders by ID (e.g. ORD-1001): item, amount, status, date."""
        order = store.get_order(customer_id, order_id)
        if order is None:
            return {"found": False, "message": f"No order {order_id} on this customer's account."}
        return {"found": True, "order": order}

    @tool
    def track_shipment(order_id: str) -> dict:
        """Get shipping/tracking status for one of the current customer's orders."""
        order = store.get_order(customer_id, order_id)
        if order is None:
            return {"found": False, "message": f"No order {order_id} on this customer's account."}
        ship = store.get_shipment(order["id"]) or {}
        return {"found": True, "order_id": order["id"], "status": order["status"], **ship}

    @tool
    def search_faq(query: str) -> dict:
        """Search the store's help-center FAQ (returns, refunds, shipping, payments, cancellations)."""
        return {"results": store.search_faq(query)}

    @tool
    def issue_refund(order_id: str, reason: str) -> dict:
        """Refund a DELIVERED order of the current customer. Large refunds need approval. Never call without the customer asking."""
        order = store.get_order(customer_id, order_id)
        if order is None:
            return {"ok": False, "error": f"Order {order_id} not found on this account."}
        if order["status"] != "delivered":
            return {"ok": False, "error": f"Only delivered orders can be refunded; {order['id']} is {order['status']}."}
        if store.refund_exists(order["id"]):
            return {"ok": False, "error": f"A refund for {order['id']} already exists."}
        store.create_refund(order["id"], order["amount"], reason, approved_by=policy.last_approver or "unknown")
        return {"ok": True, "order_id": order["id"], "amount": order["amount"],
                "message": "Refund issued. It reaches the original payment method in 5-7 business days."}

    all_tools = [lookup_order, track_shipment, search_faq, issue_refund]
    # Permission tier filter: read-only mode mein WRITE tools LLM ko dikhte hi nahi
    return [t for t in all_tools if TOOL_TIERS[t.name] <= max_tier]
