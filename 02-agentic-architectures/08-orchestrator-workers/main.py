"""Run: python 02-agentic-architectures/08-orchestrator-workers/main.py ["goal"] [--offline]

ORCH_MODEL (strong, planning) aur WORKER_MODEL (cheap, execution) alag rakh sakte ho.
"""
import argparse
import os

from orchestrator_workers import DEMO_GOAL, offline_demo_llms, orchestrate, waves

from agentkit import get_llm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("goal", nargs="?", default=DEMO_GOAL)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    if args.offline:
        orch, worker = offline_demo_llms()
    else:
        orch, worker = get_llm(os.getenv("ORCH_MODEL")), get_llm(os.getenv("WORKER_MODEL"))

    res = orchestrate(orch, worker, args.goal)
    print("=== PLAN (decided at runtime by the orchestrator) ===")
    for i, wave in enumerate(waves(res.plan.subtasks), 1):
        print(f"wave {i}: " + ", ".join(f"{s.id}<{s.worker}>" for s in wave))
    print("\n=== WORKER OUTPUTS ===")
    for r in res.results:
        print(f"\n[{r.subtask.id} / {r.subtask.worker}] ok={r.ok}\n{r.output}")
    print(f"\n=== FINAL (synthesized) ===\n{res.final}")


if __name__ == "__main__":
    main()
