"""CLI invocation modes: REPL (chat), one-shot, batch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .service import Reply, SupportDesk


def terminal_approver(tool_name: str, args: dict, description: str) -> bool:
    """Human-in-the-loop: CLI mein operator se seedha poochho."""
    ans = input(f"\n  [APPROVAL NEEDED] {description}\n  Approve? [y/N] ").strip().lower()
    return ans in ("y", "yes")


def _meta(r: Reply) -> str:
    bits = [r.request_id, f"intent={r.intent}", f"tools={r.tools_used}", f"tokens={r.tokens}"]
    if r.cost_usd is not None:
        bits.append(f"cost=${r.cost_usd:.5f}")
    for flag in ("refused", "degraded", "escalated"):
        if getattr(r, flag):
            bits.append(flag)
    return "  (" + ", ".join(bits) + f", {r.latency_ms}ms)"


def ask_once(desk: SupportDesk, customer: str, message: str, session_id: str | None = None) -> Reply:
    r = desk.handle(customer, message, session_id)
    print(r.text)
    print(_meta(r), file=sys.stderr)
    return r


def repl(desk: SupportDesk, customer: str, session_id: str | None = None) -> None:
    c = desk.store.get_customer(customer)
    print(f"ShopKart support. Logged in as {c['name'] if c else customer}. Type 'exit' to quit.")
    while True:
        try:
            msg = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if msg.lower() in ("exit", "quit"):
            break
        if not msg:
            continue
        r = desk.handle(customer, msg, session_id)
        session_id = r.session_id  # same session => memory continue
        print(f"bot> {r.text}")
        print(_meta(r), file=sys.stderr)
    print(f"session: {session_id}  (--session {session_id} se resume kar sakte ho)")


def batch(desk: SupportDesk, path: str, default_customer: str, out=sys.stdout) -> list[Reply]:
    """Har line: plain text, ya JSON {"user": "...", "message": "...", "session_id": "..."}. Output JSONL."""
    replies = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            row = json.loads(line)
            r = desk.handle(row.get("user", default_customer), row["message"], row.get("session_id"))
        else:
            r = desk.handle(default_customer, line)
        replies.append(r)
        out.write(json.dumps(r.to_dict()) + "\n")
    return replies
