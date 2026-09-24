from agentkit import ScriptedLLM
from sequential_crew import SoftwareCrew, offline_llm


def test_full_pipeline_with_one_rework():
    fake = offline_llm(qa_fails_first=True)
    res = SoftwareCrew(llm_factory=lambda r: fake, verbose=False).kickoff("calculator")
    assert list(res.outputs) == ["stories", "design", "code", "qa"]
    assert res.reworks == 1 and res.qa.passed
    assert "TypeError" in res.files["calc.py"]


def test_no_rework_when_qa_passes():
    fake = offline_llm(qa_fails_first=False)
    res = SoftwareCrew(llm_factory=lambda r: fake, verbose=False).kickoff("calculator")
    assert res.reworks == 0


def test_context_passing_only_declared_dependencies():
    fake = offline_llm(qa_fails_first=False)
    SoftwareCrew(llm_factory=lambda r: fake, verbose=False).kickoff("calculator")
    first_user = {}
    for msgs in fake.calls:
        sys = msgs[0].content
        first_user.setdefault(sys.splitlines()[0], msgs[1].content)
    assert "CONTEXT" not in first_user["ROLE: Product Manager"]
    arch = first_user["ROLE: Software Architect"]
    assert "CONTEXT from 'stories'" in arch and "'design'" not in arch
    dev = first_user["ROLE: Python Developer"]
    assert "CONTEXT from 'stories'" in dev and "CONTEXT from 'design'" in dev


def test_rework_budget_stops_endless_qa_failures():
    base = offline_llm()

    def respond(messages, tools):
        if "ROLE: QA Reviewer" in messages[0].content:
            return '{"passed": false, "issues": ["still bad"]}'
        return base.chat(messages, tools)

    res = SoftwareCrew(llm_factory=lambda r: ScriptedLLM(respond), max_reworks=2, verbose=False).kickoff("x")
    assert res.reworks == 2 and not res.qa.passed


def test_each_role_gets_its_own_llm():
    seen = []
    fake = offline_llm(qa_fails_first=False)
    SoftwareCrew(llm_factory=lambda r: seen.append(r) or fake, verbose=False).kickoff("x")
    assert {"pm", "architect", "developer", "qa"} <= set(seen)
