from agentkit import ScriptedLLM
from supervisor_team import SupervisorTeam, offline_llm, search_notes


def team(fake, **kw):
    return SupervisorTeam(llm_factory=lambda r: fake, verbose=False, **kw)


def test_full_flow_with_critic_rewrite():
    res = team(offline_llm()).run("solar?")
    assert [e.worker for e in res.board] == ["researcher", "writer", "critic", "writer", "critic"]
    assert res.stopped_reason == "finish"
    assert "6-10 years" in res.answer


def test_worker_gets_only_relevant_context():
    fake = offline_llm()
    team(fake).run("solar?")
    critic_inputs = [m[-1].content for m in fake.calls if m[0].content.startswith("ROLE: Critic")]
    assert "DRAFT:" in critic_inputs[0] and "RESEARCH:" in critic_inputs[0]
    researcher_inputs = [m[1].content for m in fake.calls if m[0].content.startswith("ROLE: Researcher")]
    assert "DRAFT" not in researcher_inputs[0]


def test_stuck_guard_forces_finish():
    def respond(messages, tools):
        if "ROLE: Supervisor" in messages[0].content:
            return '{"next": "writer", "instruction": "again"}'
        return "draft"

    res = team(ScriptedLLM(respond), max_same_worker=2).run("q")
    assert res.stopped_reason == "stuck" and len(res.board) == 2


def test_max_rounds_guard():
    order = iter(["researcher", "writer"] * 10)

    def respond(messages, tools):
        if "ROLE: Supervisor" in messages[0].content:
            return '{"next": "%s"}' % next(order)
        return "x"

    res = team(ScriptedLLM(respond), max_rounds=4).run("q")
    assert res.stopped_reason == "max_rounds" and len(res.board) == 4


def test_search_tool():
    assert "6-10" in search_notes.run({"query": "solar"})
    assert "No notes" in search_notes.run({"query": "nuclear"})
