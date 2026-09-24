"""Tree of Thoughts on the Game of 24.

    python 02-agentic-architectures/10-tree-of-thoughts/main.py 4 9 10 13
    python 02-agentic-architectures/10-tree-of-thoughts/main.py 4 9 10 13 --search dfs
    python 02-agentic-architectures/10-tree-of-thoughts/main.py --offline
"""
from __future__ import annotations

import argparse
import re
from fractions import Fraction

from agentkit import ScriptedLLM, Tracer, get_llm

from tot_game24 import State, all_next_steps, solvable
from tot_search import TreeOfThoughts


def fake_llm() -> ScriptedLLM:
    """Offline 'LLM': proposer saare valid steps deta hai (+1 galat arithmetic line, validator ko test karne),
    evaluator brute force se sure/impossible bolta hai. Asli LLM noisy hota hai; yahan hum sirf SEARCH
    mechanics dekh rahe hain."""

    def respond(messages, tools):
        prompt = messages[-1].content or ""
        nums_txt = re.search(r"Numbers left: (.*)", prompt).group(1).strip()
        st = State(tuple(Fraction(x) for x in nums_txt.split()))
        if "Propose" in prompt:
            first = nums_txt.split()[:2]
            bogus = f"{first[0]} + {first[1]} = 999" if len(first) == 2 else ""
            return "\n".join([bogus] + all_next_steps(st))
        return "Let me think... " + ("sure" if solvable(st.numbers) else "impossible")

    return ScriptedLLM(respond)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("numbers", nargs="*", type=int, default=[4, 9, 10, 13])
    ap.add_argument("--search", choices=["bfs", "dfs"], default="bfs")
    ap.add_argument("--beam", type=int, default=3)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if len(args.numbers) != 4:
        ap.error("give exactly 4 numbers")

    llm = fake_llm() if args.offline else get_llm()
    tot = TreeOfThoughts(llm, beam_width=args.beam, n_propose=8 if not args.offline else 40, tracer=Tracer(name="tot"))
    res = tot.solve_bfs(args.numbers) if args.search == "bfs" else tot.solve_dfs(args.numbers)

    print(f"\nNumbers: {args.numbers}   search={args.search}")
    if res.tree:
        for d, level in enumerate(res.tree, 1):
            print(f"  depth {d} beam: " + ", ".join(f"[{s}] v={v:g}" for s, v in level))
    print(f"\nSOLVED: {res.solved}")
    for s in res.steps:
        print(f"  {s}")
    print(f"\nllm_calls={res.llm_calls} states_explored={res.states_explored} "
          f"rejected_invalid_proposals={res.rejected_proposals}")


if __name__ == "__main__":
    main()
