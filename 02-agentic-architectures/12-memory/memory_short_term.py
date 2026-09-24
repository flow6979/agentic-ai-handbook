"""Short-term (working) memory: current conversation ka kitna hissa LLM ko bhejein.

LLM stateless hai: har call pe history khud bhejni padti hai. Context window limited hai aur
har token paisa hai. Teen strategies:

  BufferMemory         : sab kuch bhejo (simple, lekin lambi chat mein phat jayega)
  SlidingWindowMemory  : sirf last N turns (purani baatein bhool jata hai)
  SummaryMemory        : purane messages ka running summary + recent messages verbatim
"""
from __future__ import annotations

from agentkit import LLM, Message


class BufferMemory:
    def __init__(self):
        self._msgs: list[Message] = []

    def add(self, msg: Message) -> None:
        self._msgs.append(msg)

    def messages(self) -> list[Message]:
        return list(self._msgs)


class SlidingWindowMemory(BufferMemory):
    """Last `max_turns` turns rakho (1 turn = user message + uske baad ke messages)."""

    def __init__(self, max_turns: int = 3):
        super().__init__()
        self.max_turns = max_turns

    def messages(self) -> list[Message]:
        user_idx = [i for i, m in enumerate(self._msgs) if m.role == "user"]
        if len(user_idx) <= self.max_turns:
            return list(self._msgs)
        # Window hamesha USER message se shuru ho: beech se kaatne pe tool/assistant messages orphan ho jaate hain
        return self._msgs[user_idx[-self.max_turns]:]


class SummaryMemory(BufferMemory):
    """Jab messages `summarize_after` se zyada ho jaayein, purane wale summary mein fold karo."""

    SUMMARY_PROMPT = ("Update the running summary of a conversation. Keep names, preferences, decisions and open "
                      "questions. Be concise (max 5 sentences).\n\nCurrent summary:\n{summary}\n\nNew messages:\n{new}")

    def __init__(self, llm: LLM, keep_last: int = 4, summarize_after: int = 8):
        super().__init__()
        self.llm = llm
        self.keep_last = keep_last
        self.summarize_after = summarize_after
        self.summary = ""

    def add(self, msg: Message) -> None:
        super().add(msg)
        if len(self._msgs) > self.summarize_after:
            cut = len(self._msgs) - self.keep_last
            while cut < len(self._msgs) and self._msgs[cut].role != "user":  # recent part user se shuru ho
                cut += 1
            old, self._msgs = self._msgs[:cut], self._msgs[cut:]
            new = "\n".join(f"{m.role}: {m.content}" for m in old if m.content)
            self.summary = self.llm.complete(self.SUMMARY_PROMPT.format(summary=self.summary or "(empty)", new=new))

    def messages(self) -> list[Message]:
        head = [Message.system(f"Summary of the earlier conversation: {self.summary}")] if self.summary else []
        return head + list(self._msgs)
