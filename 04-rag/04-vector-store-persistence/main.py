"""Persistent RAG index on SQLite.

    python 04-rag/04-vector-store-persistence/main.py ingest                 # data/ -> rag.sqlite3
    python 04-rag/04-vector-store-persistence/main.py ingest                 # dobara: sab 'unchanged', 0 embeddings
    python 04-rag/04-vector-store-persistence/main.py search "express shipping cost"
    python 04-rag/04-vector-store-persistence/main.py ask "How long do UPI refunds take?" [--offline]
    python 04-rag/04-vector-store-persistence/main.py stats
"""
import argparse
import os
from pathlib import Path

from agentkit import Message, ScriptedLLM, get_embedder, get_llm
from vstore_sqlite import SQLiteVectorStore

HERE = Path(__file__).parent

SYSTEM = "Answer ONLY from the context. Cite sources like [shipping.md]. If missing, say you don't know."


def offline_llm(messages, tools):
    """Nakli LLM: pehla context chunk ka pehla content line + source."""
    ctx = messages[-1].content.split("QUESTION:")[0]
    first = ctx.split("\n", 2)
    src = first[1].strip("[] ") if len(first) > 1 else "?"
    body = next((l for l in ctx.splitlines()[2:] if l.strip() and not l.startswith("#")), "I don't know.")
    return f"{body} [{src}]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ingest", "search", "ask", "stats"])
    ap.add_argument("text", nargs="?")
    ap.add_argument("--db", default=str(HERE / "rag.sqlite3"))
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("-k", type=int, default=3)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    embed_name = os.getenv("EMBED_MODEL", "local")
    store = SQLiteVectorStore(args.db, get_embedder(embed_name), embed_name)
    if args.cmd == "ingest":
        print(store.ingest_folder(args.data))
    elif args.cmd == "stats":
        print(store.stats())
    elif args.cmd == "search":
        for h in store.search(args.text or "refund", args.k):
            print(f"{h.score:.3f} {h.id:24} {h.text[:70]!r}")
    else:
        if store.stats()["chunks"] == 0:
            raise SystemExit("Index empty. Run `ingest` first.")
        hits = store.search(args.text, args.k)
        ctx = "\n\n".join(f"CONTEXT\n[{h.doc_id}]\n{h.text}" for h in hits)
        llm = ScriptedLLM(offline_llm) if args.offline else get_llm()
        print(llm.chat([Message.system(SYSTEM), Message.user(f"{ctx}\n\nQUESTION: {args.text}")]).content)
    store.close()


if __name__ == "__main__":
    main()
