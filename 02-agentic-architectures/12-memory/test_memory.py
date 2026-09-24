import json

from agentkit import Message, NullTracer, ScriptedLLM, call, tool_response
from memory_assistant import PersonalAssistant
from memory_extraction import extract_facts
from memory_long_term import EpisodicMemory, SemanticMemory
from memory_short_term import BufferMemory, SlidingWindowMemory, SummaryMemory


def convo(n):
    out = []
    for i in range(n):
        out += [Message.user(f"u{i}"), Message.assistant(f"a{i}")]
    return out


def test_buffer_and_window():
    b, w = BufferMemory(), SlidingWindowMemory(max_turns=2)
    for m in convo(4):
        b.add(m)
        w.add(m)
    assert len(b.messages()) == 8
    assert [m.content for m in w.messages()] == ["u2", "a2", "u3", "a3"]
    assert w.messages()[0].role == "user"


def test_summary_memory_folds_old_messages():
    llm = ScriptedLLM(["user said u0..u2"])
    s = SummaryMemory(llm, keep_last=2, summarize_after=6)
    for m in convo(4):  # 8 messages -> 7th add triggers summary
        s.add(m)
    msgs = s.messages()
    assert msgs[0].role == "system" and "user said u0..u2" in msgs[0].content
    assert msgs[1].role == "user"  # recent part user se shuru
    assert len(llm.calls) == 1


def test_semantic_search_dedupe_persist_delete(tmp_path):
    db = tmp_path / "f.sqlite3"
    mem = SemanticMemory(db)
    a = mem.add("u1", "User is vegetarian", "preference")
    mem.add("u1", "User works as a backend engineer at a startup", "work")
    mem.add("u2", "User is vegetarian")  # doosra user: isolation
    assert mem.add("u1", "User is vegetarian", "preference") == a  # exact dup -> same id, update
    assert len(mem.all("u1")) == 2
    hits = SemanticMemory(db).search("u1", "what food does the user eat? vegetarian?", k=1)  # naya instance = persist
    assert hits[0].text == "User is vegetarian"
    mem.delete(a)
    assert [f.text for f in mem.all("u1")] == ["User works as a backend engineer at a startup"]


def test_episodic(tmp_path):
    ep = EpisodicMemory(tmp_path / "e.jsonl")
    ep.log("u1", "first")
    ep.log("u2", "other")
    ep.log("u1", "second")
    assert [e["summary"] for e in ep.recent("u1", 5)] == ["first", "second"]


def test_extract_facts_structured():
    llm = ScriptedLLM([json.dumps({"facts": [{"text": "User lives in Pune", "category": "personal"}]})])
    facts = extract_facts(llm, [Message.user("I live in Pune"), Message.assistant("Nice!")])
    assert facts[0].text == "User lives in Pune" and facts[0].category == "personal"
    assert extract_facts(llm, []) == []


def test_assistant_remembers_across_sessions(tmp_path):
    llm = ScriptedLLM([
        tool_response(call("remember", fact="User is vegetarian")), "noted",
        json.dumps({"facts": [{"text": "User lives in Pune", "category": "personal"}]}),
        "Session: user shared diet and city.",
        "Paneer tikka in Pune!",
    ])
    a1 = PersonalAssistant(llm, "u", tmp_path, tracer=NullTracer())
    a1.chat("I'm vegetarian, I live in Pune")
    out = a1.end_session()
    assert out["facts"] == ["User lives in Pune"]

    a2 = PersonalAssistant(llm, "u", tmp_path, tracer=NullTracer())
    assert a2.chat("dinner idea? vegetarian food in pune") == "Paneer tikka in Pune!"
    sp = a2.last_system_prompt
    assert "User is vegetarian" in sp and "User lives in Pune" in sp  # hot-path + background facts
    assert "Session: user shared diet and city." in sp  # episodic
