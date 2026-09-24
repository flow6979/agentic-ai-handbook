"""Group chat (AutoGen-style, from scratch): trip-planning team ek shared conversation mein.

     shared transcript (sab dekhte hain)
   +-------------------------------------+
   | user: plan 3 days in Goa, 30k budget |
   | planner: day 1 ...                   |
   | budget_keeper: over by 5k ...        |
   | local_guide: ...                     |
   +-------------------------------------+
            ^              |
            | message      | next speaker kaun?  <- SpeakerSelector
            |              v
      [ planner | budget_keeper | local_guide ]

Speaker selection strategies:
  RoundRobinSelector  -> baari baari (predictable, sasta)
  RuleBasedSelector   -> rules: '@name' mention ya keywords (sasta, deterministic)
  LLMSelector         -> ek LLM transcript padh ke decide karta hai (flexible, extra cost)

Termination: 'TERMINATE' keyword, consensus (sab 'AGREE'), ya max_turns.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from pydantic import BaseModel

from agentkit import LLM, Message, ScriptedLLM, Tracer, get_llm, llm_json


def llm_for(role: str) -> LLM:
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


@dataclass
class ChatMessage:
    speaker: str
    content: str


@dataclass
class Participant:
    name: str
    description: str  # selector isi se samajhta hai ki kab bulana hai
    system_prompt: str
    llm: LLM

    def speak(self, transcript: list[ChatMessage]) -> str:
        # Sab participants SAME shared transcript dekhte hain (shared context)
        convo = "\n".join(f"{m.speaker}: {m.content}" for m in transcript)
        prompt = (f"Group conversation so far:\n{convo}\n\nYou are {self.name}. Write your next message only "
                  "(no name prefix). Say AGREE if you accept the current plan as final.")
        return self.llm.chat([Message.system(self.system_prompt), Message.user(prompt)], temperature=0.3).content or ""


# --------------------------------------------------------------------------- speaker selection
class SpeakerSelector(Protocol):
    def next(self, transcript: list[ChatMessage], participants: list[Participant]) -> Participant: ...


class RoundRobinSelector:
    def __init__(self):
        self.i = 0

    def next(self, transcript, participants):
        p = participants[self.i % len(participants)]
        self.i += 1
        return p


class RuleBasedSelector:
    """1) '@name' mention wins  2) keyword rules  3) fallback round-robin."""

    def __init__(self, keyword_rules: dict[str, list[str]]):
        self.rules = keyword_rules
        self.fallback = RoundRobinSelector()

    def next(self, transcript, participants):
        by_name = {p.name: p for p in participants}
        last = transcript[-1]
        mention = re.search(r"@(\w+)", last.content)
        if mention and mention.group(1) in by_name and mention.group(1) != last.speaker:
            return by_name[mention.group(1)]
        for name, words in self.rules.items():
            if name != last.speaker and any(w in last.content.lower() for w in words):
                return by_name[name]
        candidates = [p for p in participants if p.name != last.speaker] or participants
        return self.fallback.next(transcript, candidates)


class NextSpeaker(BaseModel):
    name: str
    reason: str = ""


class LLMSelector:
    """Ek 'manager' LLM decide karta hai. Invalid naam aaye to round-robin fallback."""

    def __init__(self, llm: LLM):
        self.llm = llm
        self.fallback = RoundRobinSelector()

    def next(self, transcript, participants):
        roster = "\n".join(f"- {p.name}: {p.description}" for p in participants)
        convo = "\n".join(f"{m.speaker}: {m.content}" for m in transcript[-8:])  # sirf recent -> cost control
        try:
            pick = llm_json(self.llm, f"Participants:\n{roster}\n\nRecent conversation:\n{convo}\n\n"
                                      "Who should speak next? Do not pick the last speaker.", NextSpeaker,
                            system="ROLE: Chat Manager\nYou select the next speaker in a group chat.")
            match = [p for p in participants if p.name == pick.name]
            if match:
                return match[0]
        except ValueError:
            pass
        return self.fallback.next(transcript, participants)


# --------------------------------------------------------------------------- the chat
@dataclass
class ChatResult:
    transcript: list[ChatMessage]
    stopped_reason: str  # terminate | consensus | max_turns
    turns: int


@dataclass
class GroupChat:
    participants: list[Participant]
    selector: SpeakerSelector
    max_turns: int = 10
    terminate_word: str = "TERMINATE"
    consensus_word: str = "AGREE"
    verbose: bool | None = None
    tracer: Tracer = field(init=False)

    def __post_init__(self):
        self.tracer = Tracer(name="groupchat", verbose=self.verbose)

    def _consensus(self, transcript: list[ChatMessage]) -> bool:
        """Consensus = har participant ka LATEST message AGREE kehta hai."""
        latest = {m.speaker: m.content for m in transcript if m.speaker != "user"}
        return len(latest) == len(self.participants) and all(self.consensus_word in c for c in latest.values())

    def run(self, task: str) -> ChatResult:
        transcript = [ChatMessage("user", task)]
        for turn in range(1, self.max_turns + 1):
            speaker = self.selector.next(transcript, self.participants)
            text = speaker.speak(transcript)
            transcript.append(ChatMessage(speaker.name, text))
            self.tracer.event("llm", f"{speaker.name}: {text}", turn=turn)
            if self.terminate_word in text:
                return ChatResult(transcript, "terminate", turn)
            if self._consensus(transcript):
                return ChatResult(transcript, "consensus", turn)
        return ChatResult(transcript, "max_turns", self.max_turns)


# --------------------------------------------------------------------------- trip team
def trip_team(llm_factory: Callable[[str], LLM] = llm_for) -> list[Participant]:
    return [
        Participant("planner", "drafts and revises the day-by-day itinerary",
                    "ROLE: Planner\nYou draft day-by-day trip itineraries and revise them based on feedback.", llm_factory("planner")),
        Participant("budget_keeper", "checks costs against the budget, flags overspend",
                    "ROLE: Budget Keeper\nYou estimate costs in INR and flag anything over budget. Mention @planner for changes.",
                    llm_factory("budget_keeper")),
        Participant("local_guide", "suggests local, authentic spots and timing tips",
                    "ROLE: Local Guide\nYou suggest authentic local places, food and best timings.", llm_factory("local_guide")),
    ]


TRIP_RULES = {"budget_keeper": ["cost", "price", "inr", "budget", "₹"], "local_guide": ["food", "beach", "local"]}


def offline_llm() -> ScriptedLLM:
    """Fake: planner draft -> budget flags -> planner revises -> sab AGREE."""
    counts: dict[str, int] = {}

    def respond(messages, tools):
        system = messages[0].content
        if "ROLE: Chat Manager" in system:
            convo = messages[-1].content.split("Recent conversation:")[1].split("Who should speak next?")[0]
            last_speaker = [l.split(":")[0] for l in convo.strip().splitlines() if ":" in l][-1]
            order = {"user": "planner", "planner": "budget_keeper", "budget_keeper": "local_guide", "local_guide": "planner"}
            return '{"name": "%s", "reason": "next in flow"}' % order.get(last_speaker, "planner")
        role = system.splitlines()[0].replace("ROLE: ", "")
        n = counts[role] = counts.get(role, 0) + 1
        script = {
            "Planner": ["Day 1 North Goa beaches, Day 2 Old Goa churches, Day 3 South Goa. Hotel 12k, scooter 3k, cost check please.",
                        "Revised: cheaper homestay 7k instead of hotel. AGREE"],
            "Budget Keeper": ["Estimated cost INR 35k, over the 30k budget by 5k. @planner cut the hotel cost.", "Now ~30k. AGREE"],
            "Local Guide": ["Try fish thali at a local shack and Palolem beach at sunset.", "Plan looks good. AGREE"],
        }[role]
        return script[min(n, len(script)) - 1]

    return ScriptedLLM(respond)
