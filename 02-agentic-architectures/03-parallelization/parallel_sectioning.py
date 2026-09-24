"""Parallelization type 1: SECTIONING.

Ek kaam ke independent hisse ek saath (concurrently) chalao, phir results jodo.
Example: code review -> security, performance, readability reviewers PARALLEL mein.

                 +--> security reviewer ----+
    code  ------>+--> performance reviewer -+--> aggregator --> final report
                 +--> readability reviewer -+

Do implementations dikhaye hain:
- ThreadPoolExecutor (sync code ke liye simplest; LLM calls IO-bound hain to threads kaafi hain)
- asyncio.gather + asyncio.to_thread (async apps / FastAPI ke andar)
"""
from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from agentkit import LLM, ScriptedLLM, llm_json

ASPECTS: dict[str, str] = {
    "security": "You are an application security reviewer. Look for injection, secrets, unsafe deserialization, auth bugs.",
    "performance": "You are a performance reviewer. Look for N+1 queries, needless loops, blocking IO, big memory use.",
    "readability": "You are a readability reviewer. Look for unclear names, long functions, missing error handling.",
}


class AspectReview(BaseModel):
    aspect: str
    severity: Literal["none", "low", "medium", "high"]
    findings: list[str]


class ReviewReport(BaseModel):
    reviews: list[AspectReview]
    failed_aspects: list[str]
    overall: Literal["approve", "request_changes"]
    seconds: float


def review_aspect(llm: LLM, aspect: str, code: str) -> AspectReview:
    r = llm_json(llm, f"Review ONLY for {aspect}. aspect field must be '{aspect}'.\n\n```\n{code}\n```",
                 AspectReview, system=ASPECTS[aspect])
    r.aspect = aspect  # model pe bharosa mat karo, known value set karo
    return r


def aggregate(reviews: list[AspectReview], failed: list[str], seconds: float) -> ReviewReport:
    """Aggregator = plain code here. (LLM bhi ho sakta hai agar summary likhni ho.)"""
    blocking = any(r.severity in ("medium", "high") for r in reviews) or bool(failed)
    return ReviewReport(reviews=reviews, failed_aspects=failed, overall="request_changes" if blocking else "approve",
                        seconds=round(seconds, 3))


def review_code_threads(llm: LLM, code: str, max_workers: int = 3) -> ReviewReport:
    start = time.perf_counter()
    reviews, failed = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {aspect: pool.submit(review_aspect, llm, aspect, code) for aspect in ASPECTS}
        for aspect, fut in futures.items():
            try:
                reviews.append(fut.result(timeout=120))
            except Exception:  # ek reviewer fail hua to baaki ka kaam mat phenko
                failed.append(aspect)
    return aggregate(reviews, failed, time.perf_counter() - start)


async def review_code_async(llm: LLM, code: str) -> ReviewReport:
    start = time.perf_counter()
    # agentkit ka LLM sync hai, isliye to_thread. Native async client ho to seedha await karo.
    tasks = [asyncio.to_thread(review_aspect, llm, a, code) for a in ASPECTS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    reviews = [r for r in results if isinstance(r, AspectReview)]
    failed = [a for a, r in zip(ASPECTS, results) if isinstance(r, BaseException)]
    return aggregate(reviews, failed, time.perf_counter() - start)


# ---- Offline demo: har reviewer 0.3s 'sochta' hai taaki parallel speedup dikhe ---------------

SAMPLE_CODE = '''def get_user(db, user_id):
    rows = db.execute("SELECT * FROM users WHERE id = " + user_id)
    for r in rows:
        for o in db.execute("SELECT * FROM orders"):
            pass
    return rows'''


def offline_demo_llm(delay: float = 0.3) -> ScriptedLLM:
    canned = {
        "security": {"severity": "high", "findings": ["SQL built by string concat -> SQL injection. Use params."]},
        "performance": {"severity": "medium", "findings": ["Orders query inside loop (N+1), and SELECT *."]},
        "readability": {"severity": "low", "findings": ["Loop variable 'o' unused; function does more than it says."]},
    }

    def fake(messages, tools):
        time.sleep(delay)
        prompt = next(m.content for m in messages if m.role == "user")
        aspect = next(a for a in canned if f"ONLY for {a}" in prompt)
        return json.dumps({"aspect": aspect, **canned[aspect]})

    return ScriptedLLM(fake)
