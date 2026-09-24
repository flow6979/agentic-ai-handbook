"""Deep research agent: plan -> search -> read -> notes -> coverage check -> (repeat) -> cited report.

Yeh 'free-form ReAct loop' nahi hai, balki ek STRUCTURED workflow hai jisme har step pe LLM
ek chhota, focused kaam karta hai (plan banao / notes nikaalo / gaps dhundho / report likho).
Fayde: predictable cost (budget), har step testable, citations traceable.

Search aur read functions INJECT hote hain (dependency injection), isliye:
  - tests mein fake functions
  - main.py mein 02-web-search aur 03-web-page-reader ke real tools
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field

from agentkit import LLM, Tracer, llm_json


# ----------------------------------------------------------- structured outputs
class Plan(BaseModel):
    sub_questions: list[str] = Field(description="3-5 focused, searchable sub-questions")


class Note(BaseModel):
    claim: str = Field(description="one factual statement taken from the page")
    source_url: str


class Notes(BaseModel):
    notes: list[Note]


class Coverage(BaseModel):
    complete: bool
    missing: list[str] = Field(default_factory=list, description="new sub-questions for gaps")


# ----------------------------------------------------------- budget + result
@dataclass
class Budget:
    """Research khatam nahi hoti, isliye hard limits: paisa aur time dono bachte hain."""

    max_searches: int = 6
    max_pages: int = 8
    max_rounds: int = 2
    searches: int = 0
    pages: int = 0

    def can_search(self) -> bool:
        return self.searches < self.max_searches

    def can_read(self) -> bool:
        return self.pages < self.max_pages


@dataclass
class ResearchResult:
    report: str
    sources: list[str]
    notes: list[Note]
    budget: Budget
    rounds: int
    skipped: list[str] = field(default_factory=list)


SearchFn = Callable[[str], list[dict]]  # query -> [{"title","url","snippet"}]
ReadFn = Callable[[str, str], str]  # (url, question) -> page text


PLAN_PROMPT = """TASK: plan
Break this research topic into 3-5 specific sub-questions that can each be answered by a web search.
Topic: {topic}"""

NOTES_PROMPT = """TASK: extract_notes
From the page below, extract up to 5 short factual notes that help answer the question.
Only use facts stated in the page. If nothing relevant, return an empty list.
Question: {question}
Page URL: {url}
<page>
{text}
</page>"""

COVERAGE_PROMPT = """TASK: coverage
Topic: {topic}
Notes collected so far:
{notes}
Are these notes enough to write a good, balanced answer? If not, list up to 3 new sub-questions for the gaps."""

REPORT_PROMPT = """TASK: write_report
Write a concise markdown research report on: {topic}
Use ONLY the numbered notes below. Cite every factual sentence with [n] where n is the source number.
Structure: a 2-3 sentence summary, then sections with headings. Do not add a sources list (it is added automatically).
Notes:
{notes}
Sources:
{sources}"""


class DeepResearcher:
    def __init__(self, llm: LLM, search: SearchFn, read: ReadFn, *, budget: Budget | None = None,
                 pages_per_query: int = 2, max_sub_questions: int = 4, tracer: Tracer | None = None):
        self.llm = llm
        self.search = search
        self.read = read
        self.budget = budget or Budget()
        self.pages_per_query = pages_per_query
        self.max_sub_questions = max_sub_questions
        self.tracer = tracer or Tracer(name="research")

    def _investigate(self, question: str, notes: list[Note], seen: set[str], skipped: list[str]) -> None:
        if not self.budget.can_search():
            self.tracer.event("info", f"search budget exhausted, skipping: {question}")
            return
        self.budget.searches += 1
        try:
            results = self.search(question)
        except Exception as e:
            skipped.append(f"search {question!r}: {e}")
            self.tracer.event("error", f"search failed: {e}")
            return
        self.tracer.event("tool", f"search({question!r}) -> {len(results)} results")
        read_here = 0
        for r in results:
            if read_here >= self.pages_per_query or not self.budget.can_read():
                break
            url = r["url"]
            if url in seen:
                continue
            seen.add(url)
            self.budget.pages += 1
            read_here += 1
            try:
                text = self.read(url, question)
            except Exception as e:  # ek page fail = research fail nahi
                skipped.append(f"{url}: {e}")
                self.tracer.event("error", f"read failed {url}: {e}")
                continue
            extracted = llm_json(self.llm, NOTES_PROMPT.format(question=question, url=url, text=text[:6000]), Notes)
            for n in extracted.notes:
                n.source_url = url  # LLM ke bataye URL pe bharosa mat karo; jo page padha wahi source
                notes.append(n)
            self.tracer.event("llm", f"{len(extracted.notes)} notes from {url}")

    def run(self, topic: str) -> ResearchResult:
        plan = llm_json(self.llm, PLAN_PROMPT.format(topic=topic), Plan)
        queue = plan.sub_questions[: self.max_sub_questions]
        self.tracer.event("info", f"plan: {queue}")

        notes: list[Note] = []
        seen: set[str] = set()
        skipped: list[str] = []
        rounds = 0
        for rounds in range(1, self.budget.max_rounds + 1):
            for q in queue:
                self._investigate(q, notes, seen, skipped)
            if not self.budget.can_search() and not self.budget.can_read():
                break
            listing = "\n".join(f"- {n.claim}" for n in notes) or "(none)"
            cov = llm_json(self.llm, COVERAGE_PROMPT.format(topic=topic, notes=listing), Coverage)
            self.tracer.event("info", f"round {rounds}: complete={cov.complete} missing={cov.missing}")
            if cov.complete or not cov.missing:
                break
            queue = cov.missing[:3]

        sources = list(dict.fromkeys(n.source_url for n in notes))  # order-preserving unique
        num = {u: i + 1 for i, u in enumerate(sources)}
        numbered = "\n".join(f"[{num[n.source_url]}] {n.claim}" for n in notes)
        src_list = "\n".join(f"[{i}] {u}" for u, i in num.items())
        if not notes:
            report = f"# {topic}\n\nNo usable sources were found within the research budget."
        else:
            report = self.llm.complete(REPORT_PROMPT.format(topic=topic, notes=numbered, sources=src_list))
            report = report.rstrip() + "\n\n## Sources\n" + "\n".join(f"{i}. {u}" for u, i in num.items())
        return ResearchResult(report, sources, notes, self.budget, rounds, skipped)

