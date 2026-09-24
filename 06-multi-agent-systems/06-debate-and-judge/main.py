"""Run:
  python 06-multi-agent-systems/06-debate-and-judge/main.py debate "Remote work is better than office work" --judges 3 [--offline]
  python 06-multi-agent-systems/06-debate-and-judge/main.py consistency "What is 6 times 7?" [--offline]
  python 06-multi-agent-systems/06-debate-and-judge/main.py moa "What is the capital of France?" [--offline]
"""
import argparse

from debate_judge import debate, llm_for, mixture_of_agents, offline_llm, self_consistency

p = argparse.ArgumentParser()
p.add_argument("mode", choices=["debate", "consistency", "moa"])
p.add_argument("text")
p.add_argument("--rounds", type=int, default=2)
p.add_argument("--judges", type=int, default=1)
p.add_argument("--samples", type=int, default=5)
p.add_argument("--offline", action="store_true")
args = p.parse_args()

fake = offline_llm(["pro", "con", "pro"]) if args.offline else None
factory = (lambda r: fake) if fake else llm_for

if args.mode == "debate":
    res = debate(args.text, args.rounds, factory, n_judges=args.judges)
    for side, arg in res.transcript:
        print(f"\n{side.upper()}: {arg}")
    v = res.verdict
    print(f"\nJudge 1: PRO {v.pro.total} vs CON {v.con.total} -> {v.winner} ({v.reasoning})")
    if res.jury_votes:
        print(f"Jury votes: {res.jury_votes}")
    print(f"=== WINNER: {res.final_winner} ===")
elif args.mode == "consistency":
    answer, votes = self_consistency(args.text, factory("solver"), args.samples)
    print(f"votes: {dict(votes)}\n=== MAJORITY ANSWER: {answer} ===")
else:
    # Proposers = alag models (env LLM_MODEL_PROPOSER1/2/3), aggregator = strongest model
    proposers = [factory(f"proposer{i}") for i in range(1, 4)]
    print(mixture_of_agents(args.text, proposers, factory("aggregator")))
