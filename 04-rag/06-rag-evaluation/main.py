"""RAG evaluation harness.

    python 04-rag/06-rag-evaluation/main.py retrieval                   # chunking configs compare (no LLM needed)
    python 04-rag/06-rag-evaluation/main.py generation --offline        # LLM-as-judge with fake LLMs
    python 04-rag/06-rag-evaluation/main.py generation                  # real LLM answers + real judge
"""
import argparse
from pathlib import Path

from agentkit import ScriptedLLM, get_embedder, get_llm
from rageval_core import (Index, RetrievalConfig, compare_configs, evaluate_generation, load_docs, load_eval_set,
                          offline_answerer, offline_judge)

HERE = Path(__file__).parent

CONFIGS = [
    RetrievalConfig("fixed-100/k3", "fixed", 100, 0, 3),
    RetrievalConfig("fixed-300/ov50/k3", "fixed", 300, 50, 3),
    RetrievalConfig("para-400/k1", "paragraph", 400, 0, 1),
    RetrievalConfig("para-400/k3", "paragraph", 400, 0, 3),
    RetrievalConfig("para-1500/k3", "paragraph", 1500, 0, 3),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["retrieval", "generation"], nargs="?", default="retrieval")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="sirf pehle N questions (real LLM pe paisa bachao)")
    args = ap.parse_args()

    docs = load_docs(HERE / "data")
    dataset = load_eval_set(HERE / "data" / "eval_set.json")
    if args.limit:
        dataset = dataset[: args.limit]
    embedder = get_embedder()

    if args.mode == "retrieval":
        print(f"{len(dataset)} labelled questions\n")
        print(f"{'config':20} {'chunks':>6} {'hit@k':>6} {'MRR':>6} {'recall':>6}")
        for r in compare_configs(docs, dataset, CONFIGS, embedder):
            print(f"{r.config:20} {r.num_chunks:6} {r.hit_rate:6.2f} {r.mrr:6.2f} {r.recall:6.2f}")
            for f in r.failures:
                print(f"{'':22}miss: {f}")
        return

    index = Index(docs, RetrievalConfig("para-400/k3"), embedder)
    if args.offline:
        answer_llm, judge_llm = ScriptedLLM(offline_answerer), ScriptedLLM(offline_judge)
    else:
        answer_llm = judge_llm = get_llm()  # production mein judge ek alag (aksar bada) model rakho
    rep = evaluate_generation(answer_llm, judge_llm, index, dataset)
    for row in rep.rows:
        print(f"F={row['faithfulness']} R={row['relevance']} C={row['correctness']}  {row['question']}")
        print(f"      -> {row['answer'][:100]}")
    print(f"\navg faithfulness={rep.faithfulness:.2f}  relevance={rep.relevance:.2f}  correctness={rep.correctness:.2f}  (1-5)")


if __name__ == "__main__":
    main()
