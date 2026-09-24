from agentkit import ScriptedLLM
from group_chat import (TRIP_RULES, ChatMessage, GroupChat, LLMSelector, Participant, RoundRobinSelector,
                        RuleBasedSelector, offline_llm, trip_team)


def chat(selector, fake, **kw):
    return GroupChat(trip_team(lambda r: fake), selector, verbose=False, **kw)


def test_llm_selector_reaches_consensus():
    fake = offline_llm()
    res = chat(LLMSelector(fake), fake).run("Goa trip")
    speakers = [m.speaker for m in res.transcript[1:]]
    assert speakers[:3] == ["planner", "budget_keeper", "local_guide"]
    assert res.stopped_reason == "consensus"


def test_round_robin_order():
    fake = offline_llm()
    res = chat(RoundRobinSelector(), fake, max_turns=3).run("Goa trip")
    assert [m.speaker for m in res.transcript[1:]] == ["planner", "budget_keeper", "local_guide"]


def test_rule_based_mention_and_keywords():
    team = trip_team(lambda r: offline_llm())
    sel = RuleBasedSelector(TRIP_RULES)
    assert sel.next([ChatMessage("budget_keeper", "@planner cut costs")], team).name == "planner"
    assert sel.next([ChatMessage("planner", "total cost is 30k INR")], team).name == "budget_keeper"
    assert sel.next([ChatMessage("planner", "try the local food")], team).name == "local_guide"
    # never picks the last speaker on fallback
    assert sel.next([ChatMessage("planner", "hello")], team).name != "planner"


def test_llm_selector_falls_back_on_invalid_name():
    team = trip_team(lambda r: offline_llm())
    sel = LLMSelector(ScriptedLLM(lambda m, t: '{"name": "ceo"}'))
    assert sel.next([ChatMessage("user", "hi")], team).name == "planner"


def test_terminate_keyword_and_max_turns():
    p = [Participant("a", "", "ROLE: A", ScriptedLLM(lambda m, t: "done TERMINATE"))]
    assert GroupChat(p, RoundRobinSelector(), verbose=False).run("x").stopped_reason == "terminate"
    q = [Participant("a", "", "ROLE: A", ScriptedLLM(lambda m, t: "blah")),
         Participant("b", "", "ROLE: B", ScriptedLLM(lambda m, t: "blah"))]
    res = GroupChat(q, RoundRobinSelector(), max_turns=4, verbose=False).run("x")
    assert res.stopped_reason == "max_turns" and res.turns == 4


def test_every_participant_sees_shared_transcript():
    fake = offline_llm()
    chat(RoundRobinSelector(), fake, max_turns=3).run("Goa trip")
    guide_prompt = [c for c in fake.calls if "ROLE: Local Guide" in c[0].content][0][-1].content
    assert "planner:" in guide_prompt and "budget_keeper:" in guide_prompt
