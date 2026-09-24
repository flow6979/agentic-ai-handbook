import re
from fractions import Fraction

from agentkit import NullTracer, ScriptedLLM
from tot_game24 import State, all_next_steps, apply_step, is_solved, solvable
from tot_search import TreeOfThoughts


def oracle_llm():
    def respond(messages, tools):
        prompt = messages[-1].content
        nums = tuple(Fraction(x) for x in re.search(r"Numbers left: (.*)", prompt).group(1).split())
        if "Propose" in prompt:
            return "garbage line\n1 + 1 = 3\n" + "\n".join(all_next_steps(State(nums)))
        return "hmm\nsure" if solvable(nums) else "no way\nimpossible"
    return ScriptedLLM(respond)


def test_validator():
    s = State.start([4, 9, 10, 13])
    child = apply_step(s, "10 - 4 = 6")
    assert child.key() == tuple(sorted(map(Fraction, [9, 13, 6])))
    assert child.history == ("10 - 4 = 6",)
    assert apply_step(s, "10 - 4 = 7") is None  # wrong arithmetic
    assert apply_step(s, "5 + 4 = 9") is None  # 5 not available
    assert apply_step(s, "no step here") is None
    assert apply_step(State.start([1, 3]), "1 / 3 = 1/3").numbers == (Fraction(1, 3),)


def test_solvable_and_solved():
    assert solvable(tuple(map(Fraction, [4, 9, 10, 13])))
    assert not solvable(tuple(map(Fraction, [1, 1, 1, 1])))
    assert is_solved(State((Fraction(24),)))


def test_bfs_finds_solution_and_rejects_bad_proposals():
    res = TreeOfThoughts(oracle_llm(), beam_width=2, n_propose=40, tracer=NullTracer()).solve_bfs([4, 9, 10, 13])
    assert res.solved and len(res.steps) == 3
    assert res.steps[-1].endswith("= 24")
    assert res.rejected_proposals >= 2  # "garbage line" + "1 + 1 = 3" each round
    # Replay the steps deterministically: must reach 24
    st = State.start([4, 9, 10, 13])
    for step in res.steps:
        st = apply_step(st, step)
    assert is_solved(st)


def test_dfs_prunes_and_solves():
    res = TreeOfThoughts(oracle_llm(), n_propose=40, tracer=NullTracer()).solve_dfs([1, 2, 3, 4])
    assert res.solved and res.steps[-1].endswith("= 24")


def test_unsolvable_returns_false():
    res = TreeOfThoughts(oracle_llm(), n_propose=40, tracer=NullTracer()).solve_bfs([1, 1, 1, 1])
    assert not res.solved and res.steps == []


def test_evaluator_parses_last_verdict_and_caches():
    llm = ScriptedLLM(["I am sure this is impossible... final: likely"])
    tot = TreeOfThoughts(llm, tracer=NullTracer())
    from tot_search import ToTResult
    r = ToTResult(False, [])
    st = State.start([2, 3, 4])
    assert tot.evaluate(st, r) == 1.0  # last verdict word wins ("likely")
    assert tot.evaluate(st, r) == 1.0 and r.llm_calls == 1  # cached, no second call
