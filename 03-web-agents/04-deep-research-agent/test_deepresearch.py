import re

from agentkit import NullTracer
from deepresearch_agent import Budget, DeepResearcher
from deepresearch_fixtures import PAGES, fake_read, fake_search, offline_llm


def run(budget=None, search=fake_search, read=fake_read):
    return DeepResearcher(offline_llm(), search, read, budget=budget, tracer=NullTracer()).run("solar power")


def test_full_pipeline_iterates_until_coverage_complete():
    res = run()
    assert res.rounds == 2  # round 1 missed storage -> coverage asked for it -> round 2 found it
    assert "https://grid.example/storage" in res.sources
    assert "## Sources" in res.report


def test_every_citation_number_maps_to_a_source():
    res = run()
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", res.report)}
    assert cited and max(cited) <= len(res.sources)


def test_source_urls_come_from_pages_read_not_from_llm():
    res = run()
    assert all(n.source_url in PAGES for n in res.notes)  # fixture LLM claims i-made-this-up.example


def test_no_page_read_twice():
    res = run()
    assert len(res.sources) == len(set(res.sources))


def test_budget_is_enforced():
    budget = Budget(max_searches=1, max_pages=1, max_rounds=3)
    res = run(budget)
    assert budget.searches == 1 and budget.pages == 1 and len(res.sources) <= 1


def test_failing_page_is_skipped_not_fatal():
    def flaky_read(url, q):
        if "solar-cost" in url:
            raise TimeoutError("slow site")
        return fake_read(url, q)

    res = run(read=flaky_read)
    assert any("solar-cost" in s for s in res.skipped)
    assert res.notes  # other pages still produced notes


def test_no_results_gives_honest_report():
    res = run(search=lambda q: [])
    assert "No usable sources" in res.report and res.sources == []
