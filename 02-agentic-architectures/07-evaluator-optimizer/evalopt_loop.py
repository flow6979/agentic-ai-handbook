"""Evaluator-Optimizer: ek LLM likhta hai (generator), doosra rubric pe judge karta hai (evaluator),
feedback wapas generator ko, loop jab tak pass na ho ya budget khatam na ho.

    brief --> [generator] --> draft --> [hard checks (code)] --> [evaluator LLM, rubric]
                  ^                                                     |
                  +----------------- feedback (agar fail) --------------+
                                                                        |
                                              pass / max_iters / no improvement --> best draft

Project: product launch TWEET polish karna. Hard checks code mein (<=280 chars, hashtags <= 2),
soft quality (clarity, hook, CTA) LLM evaluator se.

Stop criteria (teen, production mein teeno lagao):
  1. passed          -> evaluator ne sab criteria >= threshold diye
  2. max_iters       -> cost/latency budget
  3. no improvement  -> score badh nahi raha, aage loop = paisa barbaad
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agentkit import LLM, ScriptedLLM, llm_json

RUBRIC = {
    "clarity": "Is it instantly clear what the product does?",
    "hook": "Does the first line grab attention?",
    "cta": "Is there a clear call to action?",
}


class Evaluation(BaseModel):
    scores: dict[str, int] = Field(description="criterion -> score 1..10")
    feedback: str = Field(description="specific, actionable changes for the writer")


@dataclass
class Attempt:
    draft: str
    hard_errors: list[str]
    scores: dict[str, int]
    feedback: str

    @property
    def total(self) -> int:
        return sum(self.scores.values()) if not self.hard_errors else -1


@dataclass
class OptimizeResult:
    best: Attempt
    history: list[Attempt] = field(default_factory=list)
    stop_reason: str = ""


def hard_checks(tweet: str, max_chars: int = 280, max_hashtags: int = 2) -> list[str]:
    """Deterministic rules code se check karo; LLM se yeh mat puchho (woh count mein kharab hai)."""
    errs = []
    if len(tweet) > max_chars:
        errs.append(f"too long: {len(tweet)} chars > {max_chars}")
    if len(re.findall(r"#\w+", tweet)) > max_hashtags:
        errs.append(f"more than {max_hashtags} hashtags")
    if not tweet.strip():
        errs.append("empty")
    return errs


def generate(llm: LLM, brief: str, previous: Attempt | None) -> str:
    prompt = f"Write ONE launch tweet for: {brief}\nReturn only the tweet text."
    if previous:
        problems = "; ".join(previous.hard_errors) or previous.feedback
        prompt += f"\n\nYour previous tweet:\n{previous.draft}\nFix these problems: {problems}"
    return llm.complete(prompt, system="You are a punchy B2B copywriter.", temperature=0.7).strip()


def evaluate(llm: LLM, brief: str, tweet: str) -> Evaluation:
    rubric = "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
    ev = llm_json(llm, f"Brief: {brief}\nTweet:\n{tweet}\n\nScore each criterion 1-10:\n{rubric}", Evaluation,
                  system="You are a strict marketing editor. Be critical; 8+ means genuinely great.")
    ev.scores = {k: int(ev.scores.get(k, 0)) for k in RUBRIC}  # missing criterion = 0 (strict)
    return ev


def optimize(gen_llm: LLM, eval_llm: LLM, brief: str, threshold: int = 8, max_iters: int = 4, patience: int = 2) -> OptimizeResult:
    history: list[Attempt] = []
    best: Attempt | None = None
    since_improved = 0
    prev: Attempt | None = None
    for _ in range(max_iters):
        draft = generate(gen_llm, brief, prev)
        errs = hard_checks(draft)
        if errs:  # hard fail -> evaluator LLM pe paisa mat kharch karo
            att = Attempt(draft, errs, {k: 0 for k in RUBRIC}, "")
        else:
            ev = evaluate(eval_llm, brief, draft)
            att = Attempt(draft, [], ev.scores, ev.feedback)
        history.append(att)
        prev = att

        if best is None or att.total > best.total:
            best, since_improved = att, 0
        else:
            since_improved += 1

        if not att.hard_errors and all(s >= threshold for s in att.scores.values()):
            return OptimizeResult(att, history, "passed")
        if since_improved >= patience:
            return OptimizeResult(best, history, "no_improvement")
    return OptimizeResult(best, history, "max_iters")


# ---- Offline demo ----------------------------------------------------------------------------

DEMO_BRIEF = "Snapdeploy - deploy any GitHub repo to production in 60 seconds, free tier available"


def offline_demo_llms() -> tuple[ScriptedLLM, ScriptedLLM]:
    gen = ScriptedLLM([
        "Snapdeploy is a new tool for deployments. " * 8 + "#devops #cloud #startup",  # too long + 3 hashtags
        "Snapdeploy deploys GitHub repos. It is fast.",
        "Stop babysitting deploys. Snapdeploy ships any GitHub repo to prod in 60s. Free tier -> snapdeploy.dev #devops",
    ])
    ev = ScriptedLLM([
        json.dumps({"scores": {"clarity": 7, "hook": 3, "cta": 2}, "feedback": "Weak hook, no CTA. Lead with the pain."}),
        json.dumps({"scores": {"clarity": 9, "hook": 8, "cta": 8}, "feedback": "Great."}),
    ])
    return gen, ev
