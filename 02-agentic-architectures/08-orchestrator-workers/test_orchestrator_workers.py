import json

import pytest
from orchestrator_workers import DEMO_GOAL, Subtask, make_plan, offline_demo_llms, orchestrate, waves

from agentkit import ScriptedLLM


def test_end_to_end_plan_workers_synthesis():
    orch, worker = offline_demo_llms()
    res = orchestrate(orch, worker, DEMO_GOAL)
    assert [s.id for s in res.plan.subtasks] == ["pricing", "risks", "hero"]
    assert all(r.ok for r in res.results), [r.output for r in res.results]
    assert len(worker.calls) == 3
    # synthesizer ko saare worker outputs mile
    synth_prompt = orch.calls[1][-1].content
    assert "Vercel" in synth_prompt and "Cold starts" in synth_prompt and "Ship in 60 seconds" in synth_prompt


def test_waves_respect_dependencies_and_detect_cycles():
    a, b, c = Subtask(id="a", worker="writer", instruction=""), Subtask(id="b", worker="writer", instruction="", depends_on=["a"]), \
        Subtask(id="c", worker="writer", instruction="")
    assert [[s.id for s in w] for w in waves([a, b, c])] == [["a", "c"], ["b"]]
    x = Subtask(id="x", worker="w", instruction="", depends_on=["y"])
    y = Subtask(id="y", worker="w", instruction="", depends_on=["x"])
    with pytest.raises(ValueError, match="cycle"):
        waves([x, y])


def test_plan_is_sanitised():
    raw = {"subtasks": [
        {"id": f"t{i}", "worker": "wizard" if i == 0 else "writer", "instruction": "do", "depends_on": ["ghost", f"t{i}"]}
        for i in range(10)
    ]}
    plan = make_plan(ScriptedLLM([json.dumps(raw)]), "goal", max_subtasks=4)
    assert len(plan.subtasks) == 4
    assert plan.subtasks[0].worker == "generalist"
    assert all(s.depends_on == [] for s in plan.subtasks)


def test_worker_failure_is_isolated():
    plan = {"subtasks": [{"id": "a", "worker": "writer", "instruction": "ok"}, {"id": "b", "worker": "writer", "instruction": "boom"}]}
    orch = ScriptedLLM([json.dumps(plan), "final"])

    def worker(messages, tools):
        if "boom" in messages[-1].content:
            raise RuntimeError("provider down")
        return "fine"

    res = orchestrate(orch, ScriptedLLM(worker), "g")
    assert [r.ok for r in res.results] == [True, False]
    assert "[FAILED]" in orch.calls[1][-1].content
