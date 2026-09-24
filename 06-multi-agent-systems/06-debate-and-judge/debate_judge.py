"""Debate + judge, jury, self-consistency, mixture-of-agents.

1) DEBATE: do (ya zyada) debaters rounds mein argue karte hain, har round mein opponent ka
   pichhla argument dekh ke rebut karte hain. Phir JUDGE rubric pe score deta hai.

      round 1:  PRO ──arg──►   ◄──arg── CON
      round 2:  PRO ─rebut─►   ◄─rebut─ CON
                      │ transcript
                      ▼
                   JUDGE  (rubric: evidence, logic, rebuttal) -> scores + winner

2) JURY: ek judge ki jagah kai judges (alag LLMs ideally) -> majority vote. Ek judge ka bias kam hota hai.
3) SELF-CONSISTENCY: ek hi question N baar poochho (temperature > 0), sabse common answer lo.
4) MIXTURE-OF-AGENTS: kai 'proposer' LLMs answer dete hain, ek 'aggregator' unhe mila ke best answer banata hai.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel

from agentkit import LLM, Message, ScriptedLLM, Tracer, get_llm, llm_json


def llm_for(role: str) -> LLM:
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


RUBRIC = ["evidence", "logic", "rebuttal"]


class SideScore(BaseModel):
    evidence: int  # 1-10
    logic: int
    rebuttal: int

    @property
    def total(self) -> int:
        return self.evidence + self.logic + self.rebuttal


class Verdict(BaseModel):
    pro: SideScore
    con: SideScore
    winner: Literal["pro", "con", "tie"]
    reasoning: str = ""


@dataclass
class DebateResult:
    transcript: list[tuple[str, str]]  # (side, argument)
    verdict: Verdict
    jury_votes: list[str] | None = None
    final_winner: str = ""


def debater_prompt(side: str, motion: str) -> str:
    stance = "FOR" if side == "pro" else "AGAINST"
    return (f"ROLE: Debater {side.upper()}\nYou argue {stance} the motion: '{motion}'. Max 80 words. "
            "Use concrete evidence, directly rebut the opponent's last point, never switch sides.")


JUDGE_PROMPT = ("ROLE: Judge\nYou are an impartial debate judge. Score each side 1-10 on: "
                f"{', '.join(RUBRIC)}. Judge argument quality only, not your own opinion on the motion.")


def debate(motion: str, rounds: int = 2, llm_factory: Callable[[str], LLM] = llm_for, n_judges: int = 1,
           verbose: bool | None = None) -> DebateResult:
    tracer = Tracer(name="debate", verbose=verbose)
    debaters = {"pro": llm_factory("pro"), "con": llm_factory("con")}
    transcript: list[tuple[str, str]] = []
    for r in range(1, rounds + 1):
        for side in ("pro", "con"):
            history = "\n".join(f"{s.upper()}: {a}" for s, a in transcript) or "(you open the debate)"
            arg = debaters[side].chat([Message.system(debater_prompt(side, motion)),
                                       Message.user(f"Round {r}. Debate so far:\n{history}\n\nYour argument:")]).content or ""
            transcript.append((side, arg))
            tracer.event("llm", f"R{r} {side.upper()}: {arg}")

    text = "\n".join(f"{s.upper()}: {a}" for s, a in transcript)
    verdicts = [llm_json(llm_factory(f"judge{i}" if n_judges > 1 else "judge"), f"MOTION: {motion}\n\nDEBATE:\n{text}",
                         Verdict, system=JUDGE_PROMPT) for i in range(1, n_judges + 1)]
    votes = [v.winner for v in verdicts]
    final = Counter(votes).most_common(1)[0][0]  # jury: majority vote
    return DebateResult(transcript, verdicts[0], votes if n_judges > 1 else None, final)


# --------------------------------------------------------------------------- self-consistency
def self_consistency(question: str, llm: LLM, n: int = 5) -> tuple[str, Counter]:
    """Same LLM, N samples (temperature 0.8), majority answer. Math/logic questions pe accuracy badhti hai."""
    answers = []
    for _ in range(n):
        resp = llm.chat([Message.system("Think step by step. End with a line 'ANSWER: <final answer>'."),
                         Message.user(question)], temperature=0.8)
        text = resp.content or ""
        answers.append(text.rsplit("ANSWER:", 1)[-1].strip().lower() if "ANSWER:" in text else text.strip().lower())
    votes = Counter(answers)
    return votes.most_common(1)[0][0], votes


# --------------------------------------------------------------------------- mixture of agents
def mixture_of_agents(question: str, proposers: list[LLM], aggregator: LLM) -> str:
    """Layer 1: har proposer (alag model) answer deta hai. Layer 2: aggregator sab padh ke ek behtar answer."""
    drafts = [p.complete(question, system="ROLE: Proposer\nAnswer concisely.") for p in proposers]
    joined = "\n\n".join(f"[Answer {i}]\n{d}" for i, d in enumerate(drafts, 1))
    return aggregator.complete(f"QUESTION: {question}\n\nCandidate answers:\n{joined}\n\n"
                               "Synthesize the single best answer. Fix errors, keep what is correct.",
                               system="ROLE: Aggregator\nYou merge multiple answers into one high-quality answer.")


# --------------------------------------------------------------------------- offline fake
def offline_llm(judge_winners: list[str] | None = None) -> ScriptedLLM:
    judge_iter = iter(judge_winners or ["pro"] * 10)
    sc_answers = iter(["ANSWER: 42", "ANSWER: 42", "ANSWER: 41", "ANSWER: 42", "ANSWER: 40"] * 3)

    def respond(messages, tools):
        system = messages[0].content
        if "ROLE: Debater PRO" in system:
            return "Remote work saves 1-2 hours of commute daily and widens hiring pools; the con side ignores this."
        if "ROLE: Debater CON" in system:
            return "Remote work hurts mentoring of juniors; studies show fewer spontaneous collaborations."
        if "ROLE: Judge" in system:
            w = next(judge_iter)
            hi, lo = '{"evidence": 8, "logic": 7, "rebuttal": 7}', '{"evidence": 6, "logic": 6, "rebuttal": 5}'
            pro, con = (hi, lo) if w == "pro" else (lo, hi)
            return f'{{"pro": {pro}, "con": {con}, "winner": "{w}", "reasoning": "stronger evidence"}}'
        if "Think step by step" in system:
            return f"6 x 7 ... {next(sc_answers)}"
        if "ROLE: Proposer" in system:
            return "Paris" if len(messages[-1].content) % 2 else "Paris, France"
        if "ROLE: Aggregator" in system:
            return "Paris (capital of France)."
        return "?"

    return ScriptedLLM(respond)
