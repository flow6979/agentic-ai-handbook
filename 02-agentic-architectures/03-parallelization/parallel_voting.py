"""Parallelization type 2: VOTING.

Same sawaal N baar (parallel) poochho, phir votes aggregate karo. Ek LLM call galat ho
sakti hai; majority zyada reliable hoti hai (jaise 5 moderators ki panel).

              +--> vote 1: unsafe --+
    comment --+--> vote 2: safe   --+--> majority / threshold --> decision
              +--> vote 3: unsafe --+

Variants:
- same prompt, temperature > 0 (sampling diversity)   <- yahan default
- different prompts/personas per voter
- different models per voter (sabse strong diversity)
Aggregation: majority, threshold (e.g. >=2 of 5 unsafe -> block, recall ke liye), avg score.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from agentkit import LLM, Message, ScriptedLLM, extract_json

MOD_SYSTEM = (
    "You are a content moderator for a developer forum. Label a comment 'unsafe' if it contains "
    "harassment, hate, threats, doxxing or spam; otherwise 'safe'. Reply as JSON: "
    '{"label": "safe"|"unsafe", "reason": "..."}'
)


class Vote(BaseModel):
    label: Literal["safe", "unsafe"]
    reason: str


@dataclass
class Verdict:
    decision: Literal["allow", "block"]
    votes: list[Vote]
    unsafe_count: int
    invalid: int


def one_vote(llm: LLM, comment: str, system: str = MOD_SYSTEM) -> Vote:
    resp = llm.chat([Message.system(system), Message.user(f"Comment:\n{comment}")], temperature=0.8, json_mode=True)
    return Vote.model_validate(extract_json(resp.content or ""))


def moderate(llm: LLM | list[LLM], comment: str, n: int = 5, block_threshold: int | None = None) -> Verdict:
    """`llm` list ho to har voter alag model (model diversity). threshold default = strict majority."""
    llms = llm if isinstance(llm, list) else [llm] * n
    threshold = block_threshold if block_threshold is not None else len(llms) // 2 + 1
    votes, invalid = [], 0
    with ThreadPoolExecutor(max_workers=len(llms)) as pool:
        for fut in [pool.submit(one_vote, m, comment) for m in llms]:
            try:
                votes.append(fut.result())
            except Exception:  # invalid vote ko count nahi karte (abstain)
                invalid += 1
    counts = Counter(v.label for v in votes)
    unsafe = counts.get("unsafe", 0)
    return Verdict("block" if unsafe >= threshold else "allow", votes, unsafe, invalid)


# ---- Offline demo: fake 'noisy' moderator ---------------------------------------------------


def offline_demo_llm() -> ScriptedLLM:
    """Voter i ka jawab deterministic hai (call number se), taaki 'disagreement' dikhe."""
    state = {"i": 0}
    lock = threading.Lock()
    patterns = {
        "idiot": ["unsafe", "unsafe", "safe", "unsafe", "unsafe"],
        "default": ["safe", "safe", "unsafe", "safe", "safe"],
    }

    def fake(messages, tools):
        text = messages[-1].content.lower()
        key = "idiot" if "idiot" in text else "default"
        with lock:  # voters threads mein chalte hain
            label = patterns[key][state["i"] % 5]
            state["i"] += 1
        return json.dumps({"label": label, "reason": f"voter judged {label}"})

    return ScriptedLLM(fake)
