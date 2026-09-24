"""Hybrid search playground: BM25 vs vector vs hybrid (RRF) vs hybrid + LLM rerank, side by side.

    python 04-rag/03-hybrid-search-rerank/main.py "E-1042"
    python 04-rag/03-hybrid-search-rerank/main.py "refund window" --category policy --min-year 2025
    python 04-rag/03-hybrid-search-rerank/main.py "earbuds not charging" --rerank --offline
"""
import argparse
from pathlib import Path

from agentkit import ScriptedLLM, get_embedder, get_llm
from hybrid_search import HybridRetriever, llm_rerank, load_docs, offline_reranker

DATA = Path(__file__).parent / "data" / "docs.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="NK-4471 battery life")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--category", help="metadata filter, e.g. policy / product / troubleshooting / blog")
    ap.add_argument("--min-year", type=int)
    ap.add_argument("--rerank", action="store_true", help="hybrid results ko LLM se rerank karo")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    flt = {}
    if args.category:
        flt["category"] = args.category
    if args.min_year:
        flt["year"] = (">=", args.min_year)

    r = HybridRetriever(load_docs(DATA), get_embedder())
    print(f"query: {args.query!r}   filter: {flt or '-'}\n")
    for mode in ("bm25", "vector", "hybrid"):
        res = r.search(args.query, args.k, mode, flt or None)
        print(f"{mode.upper():7}", " > ".join(x.doc.id for x in res) or "(nothing)")
    if args.rerank:
        cands = r.search(args.query, 10, "hybrid", flt or None)
        llm = ScriptedLLM(offline_reranker) if args.offline else get_llm()
        top = llm_rerank(llm, args.query, cands, top_n=args.k)
        print("RERANK ", " > ".join(x.doc.id for x in top) or "(nothing)")
    print("\nhybrid detail (bm25 rank / vector rank -> fused score):")
    for x in r.search(args.query, args.k, "hybrid", flt or None):
        print(f"  {x.doc.id:16} bm25={x.bm25_rank or '-':>2}  vec={x.vector_rank or '-':>2}  rrf={x.score:.4f}  {x.doc.text[:60]!r}")


if __name__ == "__main__":
    main()
