from agentkit import NullTracer, ScriptedLLM
from role_design import EDITOR, WRITER, Role, offline_llm, write_with_editor


def test_system_prompt_has_all_role_parts():
    sp = EDITOR.system_prompt()
    for part in ["ROLE: Editor", "GOAL:", "YOU MAY:", "YOU MUST NOT:", "OUTPUT FORMAT:", "Stay strictly in your role"]:
        assert part in sp


def test_minimal_role_prompt_skips_empty_sections():
    sp = Role(name="X", persona="p", goal="g").system_prompt()
    assert "BACKSTORY" not in sp and "TOOLS" not in sp


def test_writer_editor_revises_once_then_approves():
    fake = offline_llm()
    res = write_with_editor("APIs", llm_factory=lambda r: fake, tracer=NullTracer())
    assert [r for r, _ in res.history] == ["Writer", "Editor", "Writer", "Editor"]
    assert "menu" in res.final_text and res.rounds == 2


def test_revision_budget_terminates_even_if_never_approved():
    def respond(messages, tools):
        if "ROLE: Editor" in messages[0].content:
            return '{"approved": false, "feedback": "again"}'
        return "draft"

    fake = ScriptedLLM(respond)
    res = write_with_editor("x", llm_factory=lambda r: fake, max_revisions=1, tracer=NullTracer())
    assert res.rounds == 2  # 1 revision + final check, then stop
    assert sum(1 for r, _ in res.history if r == "Writer") == 2


def test_per_role_llm_factory_receives_role_names():
    seen = []
    fake = offline_llm()

    def factory(role):
        seen.append(role)
        return fake

    write_with_editor("x", llm_factory=factory, tracer=NullTracer())
    assert seen == ["writer", "editor"]
