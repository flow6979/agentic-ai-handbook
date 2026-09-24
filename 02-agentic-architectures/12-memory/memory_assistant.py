"""Personal assistant jo sessions ke beech user ko yaad rakhta hai.

Har turn:
  1. RETRIEVE : user message se related facts (semantic) + last episodes (episodic) nikaalo
  2. INJECT   : unhe system prompt mein daalo
  3. RESPOND  : Agent chalao (short-term window history ke saath). Agent `remember` tool se
                khud bhi fact save kar sakta hai (HOT PATH write)
Session end:
  4. EXTRACT  : poori baatcheet se facts nikaal ke save (BACKGROUND write)
  5. EPISODE  : session ka summary episodic log mein
"""
from __future__ import annotations

from pathlib import Path

from agentkit import LLM, Agent, Embedder, Message, NullTracer, Tracer, tool

from memory_extraction import extract_facts
from memory_long_term import EpisodicMemory, SemanticMemory
from memory_short_term import SlidingWindowMemory

BASE_SYSTEM = "You are a friendly personal assistant. Use what you know about the user to personalise answers."


class PersonalAssistant:
    def __init__(self, llm: LLM, user_id: str, store_dir: str | Path, *, embedder: Embedder | None = None,
                 window_turns: int = 3, tracer: Tracer | None = None):
        self.llm = llm
        self.user_id = user_id
        store = Path(store_dir)
        store.mkdir(parents=True, exist_ok=True)
        self.semantic = SemanticMemory(store / "facts.sqlite3", embedder)
        self.episodic = EpisodicMemory(store / "episodes.jsonl")
        self.short = SlidingWindowMemory(window_turns)
        self.transcript: list[Message] = []  # poora session (extraction ke liye), window se alag
        self.tracer = tracer or NullTracer(name="assistant")
        self.last_system_prompt = ""

        @tool
        def remember(fact: str, category: str = "preference") -> str:
            """Save an important long-term fact about the user (e.g. 'User is allergic to peanuts')."""
            fid = self.semantic.add(self.user_id, fact, category)
            return f"saved memory #{fid}"

        self.remember_tool = remember

    def build_system_prompt(self, user_text: str) -> str:
        # Do tarah ki retrieval:
        #  - PROFILE: preferences hamesha inject (chhoti list, har jawab pe asar daalti hai: diet, reply style)
        #  - RELEVANT: baaki facts sirf tab jab query se semantically match karein
        profile = [f for f in self.semantic.all(self.user_id) if f.category == "preference"][:10]
        relevant = self.semantic.search(self.user_id, user_text, k=5)
        seen, facts = set(), []
        for f in profile + relevant:
            if f.id not in seen:
                seen.add(f.id)
                facts.append(f)
        episodes = self.episodic.recent(self.user_id, 2)
        parts = [BASE_SYSTEM]
        if facts:
            parts.append("What you know about the user:\n" + "\n".join(f"- {f.text}" for f in facts))
        if episodes:
            parts.append("Recent past sessions:\n" + "\n".join(f"- {e['summary']}" for e in episodes))
        parts.append("If the user shares a stable new fact about themselves, call the `remember` tool.")
        return "\n\n".join(parts)

    def chat(self, user_text: str) -> str:
        self.last_system_prompt = self.build_system_prompt(user_text)
        self.tracer.event("info", f"memory context:\n{self.last_system_prompt}")
        agent = Agent(self.llm, [self.remember_tool], self.last_system_prompt, name="assistant", max_steps=4,
                      tracer=self.tracer)
        result = agent.run(user_text, history=self.short.messages())
        for m in (Message.user(user_text), Message.assistant(result.output)):
            self.short.add(m)
            self.transcript.append(m)
        return result.output

    def end_session(self) -> dict:
        """Background write: facts extract + episode summary. Returns what was stored."""
        if not self.transcript:
            return {"facts": [], "episode": None}
        facts = extract_facts(self.llm, self.transcript)
        for f in facts:
            self.semantic.add(self.user_id, f.text, f.category)
        convo = "\n".join(f"{m.role}: {m.content}" for m in self.transcript)
        episode = self.llm.complete(f"Summarise this session in one sentence for future reference:\n{convo}")
        self.episodic.log(self.user_id, episode.strip())
        self.transcript, self.short = [], SlidingWindowMemory(self.short.max_turns)
        return {"facts": [f.text for f in facts], "episode": episode.strip()}
