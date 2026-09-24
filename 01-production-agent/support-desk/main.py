"""ShopKart support agent: saare invocation modes ek entrypoint se.

  python 01-production-agent/support-desk/main.py [--offline] [--user cust_1] ask "Where is ORD-1001?"
  python 01-production-agent/support-desk/main.py repl
  python 01-production-agent/support-desk/main.py serve --port 8000
  python 01-production-agent/support-desk/main.py batch 01-production-agent/support-desk/examples/batch_input.jsonl
  python 01-production-agent/support-desk/main.py eval [--live]
  python 01-production-agent/support-desk/main.py reset-db

--offline = real LLM ki jagah keyword-based fake (koi API key nahi chahiye).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from supportdesk import Settings, SupportDesk
from supportdesk.cli import ask_once, batch, repl, terminal_approver
from supportdesk.llm_setup import ConfigError, build_llm
from supportdesk.offline import offline_llm


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Production-ready LLM-agnostic support agent")
    p.add_argument("--offline", action="store_true", help="use the scripted fake LLM (no API key needed)")
    p.add_argument("--user", default="cust_1", help="customer id (cust_1 = Asha, cust_2 = Rahul)")
    p.add_argument("--session", default=None, help="resume an existing session id")
    p.add_argument("--read-only", action="store_true", help="disable WRITE-tier tools (refunds)")
    p.add_argument("--quiet", action="store_true", help="hide per-step agent trace")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="one-shot question")
    a.add_argument("message")
    sub.add_parser("repl", help="interactive chat")
    s = sub.add_parser("serve", help="run FastAPI HTTP server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    b = sub.add_parser("batch", help="process a file of messages, print JSONL")
    b.add_argument("path")
    e = sub.add_parser("eval", help="run golden-dataset evals")
    e.add_argument("--live", action="store_true", help="use the real LLM from LLM_MODEL instead of offline fake")
    sub.add_parser("reset-db", help="delete the local SQLite db (re-seeded on next run)")
    args = p.parse_args(argv)

    settings = Settings.from_env()
    if args.read_only:
        settings = replace(settings, read_only=True)
    if args.quiet:
        settings = replace(settings, verbose=False)

    if args.cmd == "reset-db":
        Path(settings.db_path).unlink(missing_ok=True)
        print(f"deleted {settings.db_path}")
        return 0

    if args.cmd == "eval":
        from supportdesk.evals import print_report, run_evals

        try:
            factory = (lambda: build_llm(settings)) if args.live else offline_llm
            report = run_evals(factory, settings=replace(settings, verbose=False))
        except ConfigError as err:
            print(err, file=sys.stderr)
            return 2
        print_report(report)
        return 0 if report.pass_rate >= 0.8 else 1  # CI gate: 80% se neeche = fail

    try:
        llm = offline_llm() if args.offline else build_llm(settings)
    except ConfigError as err:
        print(err, file=sys.stderr)
        return 2

    interactive = args.cmd == "repl" and sys.stdin.isatty()
    desk = SupportDesk(settings, llm=llm, human_approver=terminal_approver if interactive else None)
    try:
        if args.cmd == "ask":
            ask_once(desk, args.user, args.message, args.session)
        elif args.cmd == "repl":
            repl(desk, args.user, args.session)
        elif args.cmd == "batch":
            batch(desk, args.path, args.user)
        elif args.cmd == "serve":
            import uvicorn

            from supportdesk.api import create_app

            uvicorn.run(create_app(desk), host=args.host, port=args.port)
    except PermissionError as err:
        print(f"permission denied: {err}", file=sys.stderr)
        return 3
    finally:
        desk.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
