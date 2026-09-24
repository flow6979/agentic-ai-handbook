import json

from evalopt_loop import DEMO_BRIEF, hard_checks, offline_demo_llms, optimize

from agentkit import ScriptedLLM


def test_hard_checks():
    assert hard_checks("x" * 300)[0].startswith("too long")
    assert hard_checks("a #b #c #d") == ["more than 2 hashtags"]
    assert hard_checks("fine #one") == []


def test_loop_passes_on_third_iteration():
    gen, ev = offline_demo_llms()
    res = optimize(gen, ev, DEMO_BRIEF)
    assert res.stop_reason == "passed" and len(res.history) == 3
    assert res.history[0].hard_errors and len(ev.calls) == 2  # hard-fail draft never reached the evaluator
    # evaluator ka feedback generator ke agle prompt mein gaya
    assert "Lead with the pain" in gen.calls[2][-1].content
    assert "snapdeploy.dev" in res.best.draft


def test_stops_on_no_improvement_and_keeps_best():
    gen = ScriptedLLM(["v1", "v2", "v3", "v4"])
    scores = iter([6, 5, 4, 3])
    ev = ScriptedLLM(lambda m, t: json.dumps({"scores": {"clarity": (s := next(scores)), "hook": s, "cta": s}, "feedback": "meh"}))
    res = optimize(gen, ev, "brief", patience=2, max_iters=4)
    assert res.stop_reason == "no_improvement" and res.best.draft == "v1" and len(res.history) == 3


def test_missing_criterion_counts_as_zero():
    gen = ScriptedLLM(["t1"])
    ev = ScriptedLLM([json.dumps({"scores": {"clarity": 10, "hook": 10}, "feedback": ""})])
    res = optimize(gen, ev, "b", max_iters=1)
    assert res.best.scores["cta"] == 0 and res.stop_reason == "max_iters"
