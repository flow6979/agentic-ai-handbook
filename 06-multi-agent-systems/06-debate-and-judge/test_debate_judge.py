from debate_judge import debate, mixture_of_agents, offline_llm, self_consistency


def test_debate_rounds_alternate_and_judge_scores():
    fake = offline_llm()
    res = debate("remote work", rounds=2, llm_factory=lambda r: fake, verbose=False)
    assert [s for s, _ in res.transcript] == ["pro", "con", "pro", "con"]
    assert res.verdict.winner == "pro" and res.verdict.pro.total > res.verdict.con.total
    assert res.jury_votes is None and res.final_winner == "pro"


def test_debaters_see_opponent_history():
    fake = offline_llm()
    debate("remote work", rounds=2, llm_factory=lambda r: fake, verbose=False)
    con_first = [c for c in fake.calls if "Debater CON" in c[0].content][0][-1].content
    assert "PRO:" in con_first


def test_jury_majority_vote():
    fake = offline_llm(["con", "pro", "con"])
    res = debate("x", rounds=1, llm_factory=lambda r: fake, n_judges=3, verbose=False)
    assert res.jury_votes == ["con", "pro", "con"] and res.final_winner == "con"


def test_self_consistency_majority():
    answer, votes = self_consistency("6*7?", offline_llm(), n=5)
    assert answer == "42" and votes["42"] == 3


def test_mixture_of_agents_uses_all_proposers():
    fake = offline_llm()
    out = mixture_of_agents("capital of France?", [fake, fake, fake], fake)
    agg_call = fake.calls[-1][-1].content
    assert agg_call.count("[Answer") == 3 and "Paris" in out
