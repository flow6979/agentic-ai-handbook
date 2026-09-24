"""supportdesk: production-ready, LLM-agnostic customer support agent (teaching project).

Python se use (SDK-style invocation):

    from supportdesk import SupportDesk, Settings
    desk = SupportDesk(Settings.from_env())
    reply = desk.handle("cust_1", "Where is ORD-1001?")
    print(reply.text, reply.tokens, reply.cost_usd)
"""
from .config import Settings
from .service import Reply, SupportDesk
from .store import Store

__all__ = ["Settings", "SupportDesk", "Reply", "Store"]
