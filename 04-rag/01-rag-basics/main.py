"""RAG basics demo.

    python 04-rag/01-rag-basics/main.py "How long do card refunds take?"
    python 04-rag/01-rag-basics/main.py "..." --strategy sentence --size 250 --show-chunks
    python 04-rag/01-rag-basics/main.py --compare-chunkers
    python 04-rag/01-rag-basics/main.py "..." --offline        # no API key needed
"""
import argparse
from pathlib import Path

from agentkit import ScriptedLLM, get_embedder, get_llm
from ragbasics_pipeline import CHUNKERS, build_rag, chunk_documents, load_folder, offline_answerer

DATA = Path(__file__).parent / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="How long do card refunds take?")
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--strategy", choices=list(CHUNKERS), default="recursive")
    ap.add_argument("--size", type=int, default=400)
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--show-chunks", action="store_true", help="retrieved chunks + scores print karo")
    ap.add_argument("--compare-chunkers", action="store_true")
    ap.add_argument("--offline", action="store_true", help="ScriptedLLM use karo (no key)")
    args = ap.parse_args()

    if args.compare_chunkers:
        docs = load_folder(args.data)
        for s in CHUNKERS:
            chunks = chunk_documents(docs, s, args.size)
            lens = [len(c.text) for c in chunks]
            print(f"{s:10} chunks={len(chunks):3} avg_len={sum(lens) // len(lens):4} max_len={max(lens)}")
            print(f"           first chunk: {chunks[0].text[:90]!r}")
        return

    llm = ScriptedLLM(offline_answerer) if args.offline else get_llm()
    rag = build_rag(args.data, llm, get_embedder(), args.strategy, args.size, args.k)
    ans = rag.answer(args.question)
    if args.show_chunks:
        print("--- retrieved ---")
        for c, score in ans.hits:
            print(f"{score:.3f}  {c.id:22} {c.text[:80]!r}")
        print("-----------------")
    print(ans.text)
    print("sources:", ans.sources or "-")


if __name__ == "__main__":
    main()
