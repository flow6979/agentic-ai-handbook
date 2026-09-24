"""Agentic RAG demo: two modes over two knowledge bases (hr, product).

    python 04-rag/05-agentic-rag/main.py "How many sick leave days do employees get?"            # corrective pipeline
    python 04-rag/05-agentic-rag/main.py "What is the refund window and how many sick days do employees get?" --offline
    python 04-rag/05-agentic-rag/main.py "How many vacation days do I get?" --offline              # rewrite path
    python 04-rag/05-agentic-rag/main.py "hi!" --mode agent                                        # tool-calling agent
"""
import argparse

from agentkit import ScriptedLLM, get_embedder, get_llm
from agenticrag_core import CorrectiveRAG, build_rag_agent, default_kbs, offline_agentic_llm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="How many vacation days do I get?")
    ap.add_argument("--mode", choices=["crag", "agent"], default="crag",
                    help="crag = explicit corrective pipeline, agent = LLM decides tool calls")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    llm = ScriptedLLM(offline_agentic_llm) if args.offline else get_llm()
    kbs = default_kbs(get_embedder())

    if args.mode == "agent":
        res = build_rag_agent(llm, kbs).run(args.question)
        print(f"\n{res.output}\n(steps={res.steps}, tokens in/out={res.usage.input_tokens}/{res.usage.output_tokens})")
        return

    res = CorrectiveRAG(llm, kbs).run(args.question)
    print("trace:")
    for t in res.trace:
        print("  -", t)
    print(f"\n{res.answer}")


if __name__ == "__main__":
    main()
