"""Travel & Currency Expert ko A2A server ki tarah chalao.

    python main.py                       # http://127.0.0.1:9001  (LLM = env LLM_MODEL)
    python main.py --offline             # fake LLM, no key
    python main.py --port 9001 --live-rates
    python main.py --offline --token s3cret   # card mein bearer security declare + enforce

Check:
    curl http://127.0.0.1:9001/.well-known/agent.json
    curl -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"text","text":"convert 100 USD to INR"}]}}}'
"""
from __future__ import annotations

import argparse

import uvicorn

from agentkit import get_llm

from a2a_travel_agent import create_app, offline_llm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9001)
    ap.add_argument("--offline", action="store_true", help="scripted fake LLM (no API key)")
    ap.add_argument("--live-rates", action="store_true", help="fetch real FX rates from frankfurter.app")
    ap.add_argument("--token", default=None, help="require this bearer token")
    args = ap.parse_args()
    llm = offline_llm() if args.offline else get_llm()
    app = create_app(llm, f"http://{args.host}:{args.port}/", live_rates=args.live_rates, token=args.token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
