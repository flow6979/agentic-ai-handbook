"""Reflection pattern 2: Reflexion (Shinn et al., 2023).

Self-refine mein critic ek LLM hai (subjective). Reflexion mein feedback **environment se
aata hai** (yahan: unit tests pass/fail = objective signal). Fail hone pe agent ek
"lesson" (verbal self-reflection) likhta hai, jo memory mein save hota hai aur agle
attempt ke prompt mein jaata hai.

    attempt ─► run tests ─► pass? ──yes──► done
       ▲            │no
       │            ▼
       │     reflect: "kya galat hua, agli baar kya karun"
       │            │
       └── lessons memory (JSON file: runs ke beech bhi yaad rehta hai)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from agentkit import LLM, NullTracer, Tracer

from reflection_sandbox import TestRun, run_tests

CODER_SYSTEM = "You are an expert Python programmer. Reply with ONLY one ```python code block, no explanation."
REFLECT_SYSTEM = (
    "You are reviewing your own failed attempt. In 2-3 sentences: what exactly went wrong, and a concrete "
    "lesson to apply next time. Do NOT write code."
)


class LessonMemory:
    """Lessons ki list; `path` diya to JSON file mein persist (long-term, runs ke beech)."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.lessons: list[str] = []
        if self.path and self.path.exists():
            self.lessons = json.loads(self.path.read_text())

    def add(self, lesson: str) -> None:
        self.lessons.append(lesson.strip())
        if self.path:
            self.path.write_text(json.dumps(self.lessons, indent=2))

    def render(self, last_n: int = 5) -> str:
        return "\n".join(f"- {l}" for l in self.lessons[-last_n:]) or "(none yet)"


@dataclass
class Attempt:
    code: str
    run: TestRun
    reflection: str | None = None


@dataclass
class ReflexionResult:
    solved: bool
    code: str
    attempts: list[Attempt] = field(default_factory=list)


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def solve_with_reflexion(llm: LLM, task: str, tests: list[str], *, max_attempts: int = 3,
                         memory: LessonMemory | None = None, tracer: Tracer | None = None) -> ReflexionResult:
    tracer = tracer or NullTracer(name="reflexion")
    memory = memory or LessonMemory()
    result = ReflexionResult(solved=False, code="")
    tests_txt = "\n".join(tests)

    for i in range(1, max_attempts + 1):
        prompt = (f"Task: {task}\n\nThe code must pass these tests:\n{tests_txt}\n\n"
                  f"Lessons from previous failed attempts (apply them!):\n{memory.render()}")
        code = extract_code(llm.complete(prompt, system=CODER_SYSTEM))
        run = run_tests(code, tests)
        attempt = Attempt(code, run)
        result.attempts.append(attempt)
        result.code = code
        tracer.event("result" if run.passed else "error", f"attempt {i}: passed={run.passed}\n{run.output}")
        if run.passed:
            result.solved = True
            return result
        if i < max_attempts:
            reflection = llm.complete(
                f"Task: {task}\n\nYour code:\n```python\n{code}\n```\n\nTest output:\n{run.output}",
                system=REFLECT_SYSTEM,
            )
            attempt.reflection = reflection
            memory.add(reflection)
            tracer.event("llm", f"lesson: {reflection}")
    return result
