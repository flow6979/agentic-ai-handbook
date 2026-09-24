"""Tool permission tiers + approval policy (human-in-the-loop).

  READ  tier -> data padhna (safe), hamesha allowed
  WRITE tier -> duniya badalna (paisa, emails, deletes). Policy decide karti hai:
                chhota refund = auto-approve, bada = human se poochho, human nahi = deny + escalate

Rule: LLM ko kabhi final authority mat do risky actions pe. Decision code/policy/human ka hai.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Callable

from .store import Store


class Tier(IntEnum):
    READ = 1
    WRITE = 2


TOOL_TIERS: dict[str, Tier] = {
    "lookup_order": Tier.READ,
    "track_shipment": Tier.READ,
    "search_faq": Tier.READ,
    "issue_refund": Tier.WRITE,
}

# human(tool_name, args, description) -> True/False. CLI mein input() se, API mein None.
HumanApprover = Callable[[str, dict, str], bool]


class ApprovalPolicy:
    """Agent ka `approve` hook. Har tool call se pehle chalta hai."""

    def __init__(self, store: Store, customer_id: str, auto_limit: float, human: HumanApprover | None = None):
        self.store = store
        self.customer_id = customer_id
        self.auto_limit = auto_limit
        self.human = human
        self.last_approver: str | None = None  # tool isse audit trail mein likhta hai
        self.decisions: list[dict] = []

    def __call__(self, name: str, args: dict) -> bool:
        tier = TOOL_TIERS.get(name)
        if tier is None:
            return self._record(name, False, "unknown tool: deny by default")
        if tier == Tier.READ:
            return self._record(name, True, "read tier")

        if name == "issue_refund":
            order = self.store.get_order(self.customer_id, str(args.get("order_id", "")))
            if order is None:
                # Tool khud 'not found' bolega; koi risky kaam hoga hi nahi
                return self._record(name, True, "order not found; tool will reject")
            amount = order["amount"]
            if amount <= self.auto_limit:
                self.last_approver = "auto-policy"
                return self._record(name, True, f"auto: {amount} <= {self.auto_limit}")
            desc = f"Refund ${amount:.2f} for {order['id']} ({order['item']}) - reason: {args.get('reason', '')}"
            if self.human is not None:
                ok = bool(self.human(name, args, desc))
                if ok:
                    self.last_approver = "human"
                    return self._record(name, True, "human approved")
                self.store.create_escalation(self.customer_id, f"Refund rejected by reviewer: {desc}")
                return self._record(name, False, "human rejected")
            # Koi human online nahi (API mode) -> deny + ticket, taaki koi baad mein dekhe
            self.store.create_escalation(self.customer_id, f"Refund needs manual approval: {desc}")
            return self._record(name, False, "no human available; escalated")

        return self._record(name, False, "no policy for this write tool: deny by default")

    def _record(self, name: str, ok: bool, why: str) -> bool:
        self.decisions.append({"tool": name, "approved": ok, "why": why})
        return ok
