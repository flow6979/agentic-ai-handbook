"""MCP host agent: notes + utils MCP servers se connect karke kisi bhi LLM ke saath chat.

    python main.py "Add a note to buy milk and eggs, then show my grocery notes"
    python main.py --offline "add groceries"                 # fake LLM, no key
    python main.py --offline "what is 12.5*4 + 3? calculate"
    python main.py --server docs=http://127.0.0.1:8765/mcp "..."   # extra remote server (03 wala) bhi jodo
    python main.py --prompt summarize_notes topic=work        # MCP prompt (user-controlled) se shuru karo
    python main.py --list                                     # sirf servers ke tools/resources dikhao

Destructive tools (delete_note) pe tumse y/N confirm maanga jayega.
"""
from __future__ import annotations

import argparse
import os
import sys

from agentkit import get_llm

from mcp_bridge import MCPBridge
from mcp_client_agent import build_agent, confirm_destructive, default_servers, offline_llm

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="Add a note to buy groceries (milk, eggs) and then search my grocery notes.")
    ap.add_argument("--offline", action="store_true", help="use a scripted fake LLM (no API key)")
    ap.add_argument("--server", action="append", default=[], help="extra server as name=url (Streamable HTTP)")
    ap.add_argument("--prompt", nargs="+", help="use an MCP prompt from the notes server: NAME [k=v ...]")
    ap.add_argument("--list", action="store_true", help="list tools/resources and exit")
    ap.add_argument("--db", default=os.path.join(HERE, "notes.sqlite3"))
    args = ap.parse_args()

    servers = default_servers(args.db)
    for spec in args.server:
        name, url = spec.split("=", 1)
        servers[name] = url

    llm = offline_llm() if args.offline else get_llm()
    with MCPBridge(servers) as bridge:
        if args.list:
            for t in bridge.tools():
                print(f"tool     {t.name}: {t.description}")
            for s in bridge.handles:
                for uri in bridge.list_resources(s):
                    print(f"resource {s}: {uri}")
            return

        task = args.task
        if args.prompt:
            name, *kv = args.prompt
            task = bridge.get_prompt("notes", name, dict(x.split("=", 1) for x in kv))
            print(f"[prompt {name}] -> {task}\n")

        agent = build_agent(llm, bridge, approve=confirm_destructive(bridge))
        result = agent.run(task)
        print("\n=== ANSWER ===\n" + result.output)
        print(f"\n(steps={result.steps}, tokens in/out={result.usage.input_tokens}/{result.usage.output_tokens})",
              file=sys.stderr)


if __name__ == "__main__":
    main()
