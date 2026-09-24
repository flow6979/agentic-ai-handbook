import asyncio
import json

from parallel_sectioning import SAMPLE_CODE, review_code_async, review_code_threads
from parallel_sectioning import offline_demo_llm as review_llm
from parallel_voting import Verdict, moderate
from parallel_voting import offline_demo_llm as vote_llm

from agentkit import ScriptedLLM


def test_sectioning_runs_in_parallel():
    rep = review_code_threads(review_llm(delay=0.2), SAMPLE_CODE)
    assert {r.aspect for r in rep.reviews} == {"security", "performance", "readability"}
    assert rep.overall == "request_changes"
    assert rep.seconds < 0.5  # 3 x 0.2s sequential = 0.6s


def test_sectioning_async_matches():
    rep = asyncio.run(review_code_async(review_llm(delay=0.1), SAMPLE_CODE))
    assert len(rep.reviews) == 3 and rep.seconds < 0.3


def test_one_failed_reviewer_does_not_kill_the_report():
    def fake(messages, tools):
        first = next(m.content for m in messages if m.role == "user")  # retry pe bhi original prompt
        if "ONLY for performance" in first:
            return "garbage"
        aspect = "security" if "ONLY for security" in first else "readability"
        return json.dumps({"aspect": aspect, "severity": "none", "findings": []})

    rep = review_code_threads(ScriptedLLM(fake), "x = 1")
    assert rep.failed_aspects == ["performance"]
    assert rep.overall == "request_changes"  # missing review = not safe to approve


def test_voting_majority():
    v: Verdict = moderate(vote_llm(), "you idiot")
    assert v.unsafe_count == 4 and v.decision == "block"
    v2 = moderate(vote_llm(), "nice post")
    assert v2.unsafe_count == 1 and v2.decision == "allow"


def test_voting_threshold_and_invalid_votes():
    answers = iter(['{"label":"unsafe","reason":"x"}', "oops", '{"label":"safe","reason":"y"}'])
    llm = ScriptedLLM(lambda m, t: next(answers))
    v = moderate(llm, "hmm", n=3, block_threshold=1)  # strict policy: 1 unsafe vote is enough
    assert v.invalid == 1 and v.decision == "block"


def test_voting_with_different_models():
    llms = [ScriptedLLM(['{"label":"safe","reason":"a"}']), ScriptedLLM(['{"label":"unsafe","reason":"b"}']),
            ScriptedLLM(['{"label":"unsafe","reason":"c"}'])]
    assert moderate(llms, "x").decision == "block"
