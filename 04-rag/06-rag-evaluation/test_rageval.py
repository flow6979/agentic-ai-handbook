import json
from pathlib import Path

import pytest

from agentkit import ScriptedLLM, get_embedder
from rageval_core import (EvalItem, Index, Judgement, RetrievalConfig, compare_configs, evaluate_generation,
                          evaluate_retrieval, hit_at_k, judge, load_docs, load_eval_set, offline_answerer,
                          offline_judge, recall_at_k, reciprocal_rank)

HERE = Path(__file__).parent


def test_metric_math():
    assert hit_at_k(["a", "b"], ["b"]) == 1.0 and hit_at_k(["a"], ["z"]) == 0.0
    assert reciprocal_rank(["x", "y", "b"], ["b"]) == pytest.approx(1 / 3)
    assert reciprocal_rank(["x"], ["b"]) == 0.0
    assert recall_at_k(["a", "c"], ["a", "b"]) == 0.5


def test_evaluate_retrieval_with_fake_retriever():
    data = [EvalItem("q1", ["a.md"]), EvalItem("q2", ["b.md"])]
    fake = {"q1": [("x.md", ""), ("a.md", ""), ("a.md", "")], "q2": [("x.md", "")]}
    rep = evaluate_retrieval(lambda q: fake[q], data)
    assert rep.hit_rate == 0.5 and rep.mrr == pytest.approx(0.25) and rep.failures == ["q2"]


def test_compare_configs_on_real_data():
    docs = load_docs(HERE / "data")
    data = load_eval_set(HERE / "data" / "eval_set.json")
    reps = {r.config: r for r in compare_configs(docs, data, [
        RetrievalConfig("k1", "paragraph", 400, 0, 1), RetrievalConfig("k3", "paragraph", 400, 0, 3)],
        get_embedder("local"))}
    assert reps["k3"].hit_rate >= reps["k1"].hit_rate  # zyada k = hit rate kam nahi ho sakta
    assert reps["k3"].recall >= reps["k1"].recall
    assert 0.5 <= reps["k3"].hit_rate <= 1.0


def test_judge_validates_score_range():
    llm = ScriptedLLM([json.dumps({"score": 9}), json.dumps({"score": 4, "reason": "ok"})])
    assert judge(llm, "TASK:RELEVANCE ...") == Judgement(score=4, reason="ok")  # 9 reject -> retry


def test_generation_eval_offline():
    docs = load_docs(HERE / "data")
    data = load_eval_set(HERE / "data" / "eval_set.json")[:3]
    idx = Index(docs, RetrievalConfig("p"), get_embedder("local"))
    rep = evaluate_generation(ScriptedLLM(offline_answerer), ScriptedLLM(offline_judge), idx, data)
    assert len(rep.rows) == 3
    assert all(1 <= row["faithfulness"] <= 5 for row in rep.rows)
    assert rep.faithfulness >= 4  # extractive fake answers context se hi hain


def test_offline_judge_penalises_unfaithful_answer():
    prompt = "TASK:FAITHFULNESS\nCONTEXT:\nCard refunds take 5 to 7 business days.\nANSWER: Refunds arrive instantly via crypto wallet"
    low = json.loads(offline_judge([type("M", (), {"content": prompt})()], None))["score"]
    prompt_ok = "TASK:FAITHFULNESS\nCONTEXT:\nCard refunds take 5 to 7 business days.\nANSWER: Card refunds take 5 to 7 business days"
    high = json.loads(offline_judge([type("M", (), {"content": prompt_ok})()], None))["score"]
    assert low < high
