import base64
import json

from labapi import run
from labapi.rag_lab import SAMPLE_PDF


def go(params, offline=True):
    events = []
    out = run({"lab": "rag", "params": params, "offline": offline}, events.append)
    json.dumps(events, default=str)
    json.dumps(out, default=str)
    return out, events


def stages(events):
    return [(e["stage"], e["status"]) for e in events if e.get("kind") == "stage"]


def test_ingest_sample_emits_pipeline_stages():
    out, events = go({"action": "ingest", "chunk_size": 450})
    assert out["ok"], out
    r = out["result"]
    assert r["pages"] == 4 and r["n_chunks"] > 4 and "local" in r["embedder"]
    assert ("load", "done") in stages(events) and ("embed", "done") in stages(events)


def test_ask_cites_the_right_page():
    out, events = go({"action": "ask", "question": "How many days of sick leave per year?"})
    r = out["result"]
    assert out["ok"] and 2 in r["pages"] and "12" in r["answer"]
    chunks = [e for e in events if e.get("kind") == "chunks"][0]["chunks"]
    assert chunks[0]["page"] == 2 and chunks[0]["score"] >= chunks[-1]["score"]
    assert r["llm_calls"] == 1


def test_min_score_gate_skips_llm():
    out, _ = go({"action": "ask", "question": "What is the capital of Peru?", "min_score": 0.99})
    r = out["result"]
    assert r["gated"] and r["llm_calls"] == 0 and "couldn't find" in r["answer"]


def test_no_rag_answers_without_document():
    out, events = go({"action": "ask", "no_rag": True})
    r = out["result"]
    assert r["no_rag"] and r["pages"] == [] and not [e for e in events if e.get("kind") == "chunks"]


def test_upload_and_text_sources_and_strategies():
    b64 = base64.b64encode(SAMPLE_PDF.read_bytes()).decode()
    out, _ = go({"action": "ask", "source": "upload", "pdf_b64": b64, "filename": "x.pdf", "strategy": "sentence",
                 "question": "What is the hotel cap per night in metro cities?"})
    assert out["ok"] and 3 in out["result"]["pages"]
    out, _ = go({"action": "ask", "source": "text", "text": "Refunds take 5 days.\n\nShipping is free above 500 rupees.",
                 "question": "How long do refunds take?", "strategy": "fixed"})
    assert out["ok"] and out["result"]["pages"] == [1]


def test_bad_inputs_are_structured_errors():
    out, _ = go({"action": "ingest", "source": "upload", "pdf_b64": ""})
    assert not out["ok"] and "No PDF" in out["error"]["message"]
    out, _ = go({"action": "ingest", "strategy": "magic"})
    assert not out["ok"]


def test_follow_up_is_condensed():
    out, _ = go({"action": "ask", "question": "and parental leave?",
                 "history": [{"q": "How many days of sick leave?", "a": "12 days [p.2]"}]})
    assert out["ok"] and out["result"]["standalone"] == "parental leave?"
