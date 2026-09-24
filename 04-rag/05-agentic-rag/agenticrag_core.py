"""Agentic RAG: retrieval ek fixed step nahi, ek DECISION hai.

Do styles is file mein:

A) Tool-calling agent  (build_rag_agent)
   LLM ko har knowledge base ek tool ki tarah milta hai. Woh khud decide karta hai: search karna hai ya nahi,
   kis KB mein, kitni baar, kis query se.

B) Corrective RAG pipeline  (CorrectiveRAG)  - explicit, testable graph:
   route -> decompose -> retrieve -> grade -> (rewrite + retry) -> answer -> groundedness check -> (regenerate)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from agentkit import LLM, Agent, Embedder, Message, Tool, Tracer, cosine, llm_json


# ------------------------------------------------------------ knowledge bases
@dataclass
class Passage:
    id: str
    source: str
    text: str
    score: float = 0.0


class KnowledgeBase:
    def __init__(self, name: str, description: str, folder: str | Path, embedder: Embedder):
        self.name, self.description, self.embedder = name, description, embedder
        self.passages: list[Passage] = []
        for p in sorted(Path(folder).glob("*.md")):
            paras = [x.strip() for x in p.read_text().split("\n\n") if x.strip() and not x.startswith("# ")]
            self.passages += [Passage(f"{p.name}#{i}", p.name, t) for i, t in enumerate(paras)]
        self.vectors = embedder.embed([x.text for x in self.passages])

    def search(self, query: str, k: int = 3) -> list[Passage]:
        q = self.embedder.embed_one(query)
        scored = sorted(zip(self.passages, self.vectors), key=lambda pv: cosine(q, pv[1]), reverse=True)[:k]
        return [Passage(p.id, p.source, p.text, cosine(q, v)) for p, v in scored]


def default_kbs(embedder: Embedder, root: str | Path | None = None) -> dict[str, KnowledgeBase]:
    root = Path(root or Path(__file__).parent / "data")
    return {
        "hr": KnowledgeBase("hr", "Internal employee policies: leave, sick leave, travel expenses, working hours, notice period.",
                            root / "hr", embedder),
        "product": KnowledgeBase("product", "Customer-facing NimbusKart policies: refunds, shipping, warranty, Plus membership.",
                                 root / "product", embedder),
    }


def format_passages(passages: list[Passage]) -> str:
    return "\n".join(f"[{i}] [{p.source}] {p.text}" for i, p in enumerate(passages))


# ------------------------------------------------------------ A) tool-calling agent
def make_search_tool(kb: KnowledgeBase, k: int = 3) -> Tool:
    def run(query: str) -> str:
        hits = kb.search(query, k)
        return "\n".join(f"[{h.source}] {h.text}" for h in hits) or "No results."

    return Tool(
        name=f"search_{kb.name}",
        description=f"Search the {kb.name} knowledge base. Contains: {kb.description} "
                    "Use a short, specific search query.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        fn=run,
    )


AGENT_SYSTEM = """You are NimbusKart's assistant with search tools over internal knowledge bases.
- For greetings or general chit-chat, answer directly without searching.
- For company-specific facts, ALWAYS search first. Pick the right knowledge base.
- If a question has several parts, search for each part (you may call tools several times).
- If results don't answer it, try one rephrased search, then say you couldn't find it.
- Cite sources like [leave_policy.md]. Never invent policy details."""


def build_rag_agent(llm: LLM, kbs: dict[str, KnowledgeBase], tracer: Tracer | None = None) -> Agent:
    return Agent(llm, [make_search_tool(kb) for kb in kbs.values()], AGENT_SYSTEM, name="rag-agent",
                 max_steps=6, tracer=tracer)


# ------------------------------------------------------------ B) corrective RAG pipeline
class Route(BaseModel):
    kbs: list[str]  # [] = retrieval ki zaroorat nahi
    reason: str = ""


class SubQuestions(BaseModel):
    questions: list[str]


class Grades(BaseModel):
    relevant: list[int]  # passage numbers jo sach mein sawaal ka jawab dene mein kaam aayenge


class Rewrite(BaseModel):
    query: str


class GroundCheck(BaseModel):
    grounded: bool
    unsupported: list[str] = []


ROUTE_PROMPT = """TASK:ROUTE
Decide which knowledge bases are needed to answer the question. Choose zero or more of:
{kbs}
Return an empty list if no company knowledge is needed (greetings, general knowledge).
QUESTION: {question}"""

DECOMPOSE_PROMPT = """TASK:DECOMPOSE
If the question asks several independent things, split it into standalone sub-questions (max 3).
Otherwise return it unchanged as a single item.
QUESTION: {question}"""

GRADE_PROMPT = """TASK:GRADE
Which passages contain information that helps answer the question? Return their numbers.
QUESTION: {question}
SEARCH QUERY USED: {query}
PASSAGES:
{passages}"""

REWRITE_PROMPT = """TASK:REWRITE
The search query below found nothing relevant. Rewrite it using the vocabulary a company policy document would use
(e.g. formal terms, synonyms). Return a better search query.
QUERY: {question}"""

ANSWER_PROMPT = """TASK:ANSWER
Answer the question using ONLY these passages. Cite each fact like [file.md].
{extra}
PASSAGES:
{passages}
QUESTION: {question}"""

CHECK_PROMPT = """TASK:CHECK
Is every factual claim in the ANSWER supported by the PASSAGES? List unsupported claims.
PASSAGES:
{passages}
ANSWER: {answer}"""

DIRECT_PROMPT = """TASK:DIRECT
Reply briefly. You are NimbusKart's assistant for HR and product policy questions.
MESSAGE: {question}"""

NOT_FOUND = "I couldn't find this in NimbusKart's knowledge bases."


@dataclass
class CRAGResult:
    answer: str
    route: list[str]
    sub_questions: list[str] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)
    grounded: bool | None = None
    trace: list[str] = field(default_factory=list)


class CorrectiveRAG:
    def __init__(self, llm: LLM, kbs: dict[str, KnowledgeBase], k: int = 4, max_regenerations: int = 1):
        self.llm, self.kbs, self.k, self.max_regen = llm, kbs, k, max_regenerations

    def _retrieve_graded(self, question: str, kb_names: list[str], trace: list[str]) -> list[Passage]:
        query = question
        for attempt in range(2):  # original query, phir ek rewrite
            cands = [p for name in kb_names for p in self.kbs[name].search(query, self.k)]
            grades = llm_json(self.llm, GRADE_PROMPT.format(question=question, query=query, passages=format_passages(cands)), Grades)
            good = [cands[i] for i in dict.fromkeys(grades.relevant) if 0 <= i < len(cands)]
            trace.append(f"retrieve({query!r}) -> {len(cands)} candidates, {len(good)} relevant")
            if good:
                return good
            if attempt == 0:
                query = llm_json(self.llm, REWRITE_PROMPT.format(question=question), Rewrite).query
                trace.append(f"rewrite -> {query!r}")
        # Original CRAG paper yahan web search fallback karta hai (dekho 03-web-agents)
        trace.append(f"no relevant passages for {question!r}")
        return []

    def run(self, question: str) -> CRAGResult:
        trace: list[str] = []
        valid = {n: kb.description for n, kb in self.kbs.items()}
        route = llm_json(self.llm, ROUTE_PROMPT.format(
            kbs="\n".join(f"- {n}: {d}" for n, d in valid.items()), question=question), Route)
        kb_names = [n for n in route.kbs if n in valid]  # LLM ne unknown KB bola to ignore
        trace.append(f"route -> {kb_names or 'none'} ({route.reason})")
        if not kb_names:
            return CRAGResult(self.llm.complete(DIRECT_PROMPT.format(question=question)), [], trace=trace)

        subs = llm_json(self.llm, DECOMPOSE_PROMPT.format(question=question), SubQuestions).questions[:3] or [question]
        trace.append(f"sub-questions -> {subs}")

        passages: list[Passage] = []
        for sq in subs:
            for p in self._retrieve_graded(sq, kb_names, trace):
                if p.id not in {x.id for x in passages}:
                    passages.append(p)
        if not passages:
            return CRAGResult(NOT_FOUND, kb_names, subs, [], None, trace)

        ctx = format_passages(passages)
        extra = ""
        for attempt in range(self.max_regen + 1):
            answer = self.llm.complete(ANSWER_PROMPT.format(extra=extra, passages=ctx, question=question))
            check = llm_json(self.llm, CHECK_PROMPT.format(passages=ctx, answer=answer), GroundCheck)
            trace.append(f"groundedness -> {check.grounded} {check.unsupported or ''}")
            if check.grounded:
                return CRAGResult(answer, kb_names, subs, passages, True, trace)
            extra = f"Your previous answer had unsupported claims: {check.unsupported}. Remove them."
        return CRAGResult(answer + "\n\n(Note: parts of this answer could not be verified against the sources.)",
                          kb_names, subs, passages, False, trace)


# ------------------------------------------------------------ offline fake LLM
_STOP = set("what which when where does many much with from that this have your about there their they "
            "into days more than much also need know tell please could would should".split())
HR_WORDS = {"employee", "employees", "leave", "sick", "salary", "hotel", "meal", "office", "notice", "parental",
            "expense", "expenses", "travel", "remote", "home", "vacation", "probation", "allowance"}
PRODUCT_WORDS = {"refund", "refunds", "shipping", "order", "warranty", "plus", "delivery", "express", "membership",
                 "customer", "damaged", "return"}
SYNONYMS = {"vacation": "paid leave", "holidays": "paid leave", "money back": "refund", "wfh": "work from home",
            "return": "refund"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in _STOP}


def _best_sentence(question: str, passages: list[tuple[str, str]]) -> str | None:
    q, best, score = _words(question), None, 0
    for src, text in passages:
        for sent in re.split(r"(?<=[.!?])\s+", text):
            s = len(q & _words(sent))
            if s > score:
                best, score = f"{sent.strip()} [{src}]", s
    return best


def offline_agentic_llm(messages: list[Message], tools) -> str:
    """Rule-based nakli LLM: prompt ke 'TASK:' marker se samajhta hai kya karna hai. Demo/test only."""
    from agentkit import call, tool_response

    # llm_json() prompt ke end mein JSON schema jodta hai; nakli LLM ke parsing ke liye use hata do
    last = (messages[-1].content or "").split("\n\nReturn ONLY a JSON object")[0]
    task = re.match(r"TASK:(\w+)", last)
    if task is None:  # tool-calling agent mode (A)
        user_q = next(m.content for m in reversed(messages) if m.role == "user")
        tool_msgs = [m for m in messages if m.role == "tool"]
        if not tool_msgs:
            w = set(re.findall(r"[a-z]+", user_q.lower()))
            kb = "hr" if w & HR_WORDS else "product" if w & PRODUCT_WORDS else None
            if kb is None:
                return "Hi! Ask me about NimbusKart HR or product policies."
            return tool_response(call(f"search_{kb}", query=user_q))
        pairs = re.findall(r"^\[([^\]]+)\] (.+)$", tool_msgs[-1].content or "", re.M)
        return _best_sentence(user_q, pairs) or NOT_FOUND

    kind = task.group(1)
    if kind == "ROUTE":
        q = last.rsplit("QUESTION:", 1)[-1].lower()
        w = set(re.findall(r"[a-z]+", q))
        kbs = (["hr"] if w & HR_WORDS else []) + (["product"] if w & PRODUCT_WORDS else [])
        return f'{{"kbs": {kbs}, "reason": "keyword match"}}'.replace("'", '"')
    if kind == "DECOMPOSE":
        q = last.rsplit("QUESTION:", 1)[-1].strip()
        parts = [p.strip(" ?") + "?" for p in re.split(r"\band\b", q) if len(p.split()) >= 3]
        import json
        return json.dumps({"questions": parts or [q]})
    if kind == "GRADE":
        import json
        q = _words(re.search(r"QUESTION: (.+)", last).group(1)) | _words(re.search(r"SEARCH QUERY USED: (.+)", last).group(1))
        rel = [int(i) for i, t in re.findall(r"^\[(\d+)\] \[[^\]]+\] (.+)$", last, re.M) if len(q & _words(t)) >= 2]
        return json.dumps({"relevant": rel})
    if kind == "REWRITE":
        import json
        q = last.rsplit("QUERY:", 1)[-1].strip().lower()
        for a, b in SYNONYMS.items():
            q = q.replace(a, b)
        return json.dumps({"query": q})
    if kind == "ANSWER":
        q = last.rsplit("QUESTION:", 1)[-1]
        pairs = re.findall(r"^\[\d+\] \[([^\]]+)\] (.+)$", last, re.M)
        parts = [p for p in re.split(r"\band\b", q) if len(p.split()) >= 3] or [q]
        sents = list(dict.fromkeys(s for s in (_best_sentence(p, pairs) for p in parts) if s))
        if not sents and pairs:  # words match nahi hue (e.g. "vacation"): passages grader pass kar chuke, pehla use karo
            src, text = pairs[0]
            sents = [f"{re.split(r'(?<=[.!?])\s+', text)[0]} [{src}]"]
        return " ".join(sents) or NOT_FOUND
    if kind == "CHECK":
        import json
        passages = last.split("ANSWER:")[0]
        answer = last.rsplit("ANSWER:", 1)[-1]
        claims = [re.sub(r"\s*\[[^\]]+\]", "", s).strip() for s in re.split(r"(?<=\])\s+", answer) if s.strip()]
        unsupported = [c for c in claims if c and c not in passages]
        return json.dumps({"grounded": not unsupported, "unsupported": unsupported})
    return "Hi! I answer NimbusKart HR and product policy questions."
