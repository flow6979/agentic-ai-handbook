"""Evals: agent ke liye 'unit tests', lekin behaviour-level.

Golden dataset (evals/golden.jsonl) mein har case: input + expected behaviour.
Hum score karte hain:
  - tool choice: expected tools call hue? (aur jab koi tool expected nahi, to koi call nahi hua?)
  - answer contains: reply mein zaroori facts hain?
  - refusal correctness: jo refuse hona chahiye tha woh hua, jo nahi woh nahi?

Offline mode (ScriptedLLM) = pipeline regression check, CI mein har PR pe.
Live mode (real LLM) = prompt/model change ke baad quality check. Model badla? Pehle evals chalao.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from agentkit import LLM

from .config import Settings
from .service import SupportDesk
from .store import Store

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.jsonl"


@dataclass
class CaseResult:
    id: str
    passed: bool
    checks: dict[str, bool]
    reply: str
    tools_used: list[str]


@dataclass
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 0.0

    def metric(self, name: str) -> float:
        vals = [r.checks[name] for r in self.results if name in r.checks]
        return sum(vals) / len(vals) if vals else 1.0


def load_cases(path: Path = GOLDEN) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def score_case(case: dict, reply) -> CaseResult:
    used = set(reply.tools_used)
    expected = set(case.get("expect_tools", []))
    checks = {
        "tool_choice": (not used) if not expected else expected <= used,
        "contains": all(s.lower() in reply.text.lower() for s in case.get("expect_contains", [])),
        "refusal": reply.refused == case.get("expect_refusal", False),
    }
    return CaseResult(case["id"], all(checks.values()), checks, reply.text, reply.tools_used)


def run_evals(llm_factory: Callable[[], LLM], cases: list[dict] | None = None, settings: Settings | None = None) -> EvalReport:
    base = settings or Settings.from_env(verbose=False)
    report = EvalReport()
    for case in cases or load_cases():
        # Har case fresh in-memory DB pe: ek case ka refund doosre ko affect na kare (isolation)
        desk = SupportDesk(replace(base, db_path=":memory:", trace_file=None, rate_limit_per_minute=1000),
                           llm=llm_factory(), store=Store(":memory:"))
        try:
            report.results.append(score_case(case, desk.handle(case["user"], case["input"])))
        finally:
            desk.close()
    return report


def print_report(report: EvalReport) -> None:
    for r in report.results:
        mark = "PASS" if r.passed else "FAIL"
        failed = [k for k, v in r.checks.items() if not v]
        print(f"[{mark}] {r.id:<22} tools={r.tools_used} {'failed=' + str(failed) if failed else ''}")
        if not r.passed:
            print(f"        reply: {r.reply[:160]}")
    print(f"\npass rate: {report.pass_rate:.0%} | tool_choice {report.metric('tool_choice'):.0%} | "
          f"contains {report.metric('contains'):.0%} | refusal {report.metric('refusal'):.0%}")
