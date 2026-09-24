"""Sequential crew (CrewAI-style, from scratch): software team pipeline.

    Product Manager -> Architect -> Developer -> QA Reviewer
                                       ^            |
                                       +-- rework --+   (agar QA fail kare, max 1 baar)

Concepts:
- Role  = kaun kaam karega (persona, goal, tools)
- Task  = kya kaam hai (description, expected_output, kis role ka, kin tasks ka context chahiye)
- Crew  = tasks ko order mein chalata hai, ek task ka output agle ka input (context passing)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel

from agentkit import (LLM, Agent, ScriptedLLM, Tool, Tracer, call, get_llm, llm_json, tool, tool_response)


def llm_for(role: str) -> LLM:
    """LLM_MODEL_DEVELOPER=groq:... jaise per-role override, warna LLM_MODEL."""
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


@dataclass
class Role:
    key: str  # "developer" -- llm_for() isi se model chunta hai
    title: str
    goal: str
    backstory: str
    tools: list[Tool] = field(default_factory=list)

    def system_prompt(self) -> str:
        return (
            f"ROLE: {self.title}\nGOAL: {self.goal}\nBACKSTORY: {self.backstory}\n"
            "Do only your role's job. Be concise and concrete."
        )


@dataclass
class Task:
    name: str
    description: str
    expected_output: str  # output contract: agla role isi shape pe depend karta hai
    role: Role
    context: list[str] = field(default_factory=list)  # kin pichhle tasks ka output chahiye

    def prompt(self, inputs: dict[str, str], outputs: dict[str, str]) -> str:
        parts = [f"TASK: {self.description.format(**inputs)}", f"EXPECTED OUTPUT: {self.expected_output}"]
        for dep in self.context:  # sirf declared context -> 'context bleeding' kam
            parts.append(f"--- CONTEXT from '{dep}' ---\n{outputs[dep]}")
        return "\n\n".join(parts)


class QAVerdict(BaseModel):
    passed: bool
    issues: list[str] = []


# --------------------------------------------------------------------------- developer's tool
class Workspace:
    """Developer ka 'file system' (in-memory). Real mein yeh repo / sandbox hota."""

    def __init__(self):
        self.files: dict[str, str] = {}

    def as_tool(self) -> Tool:
        files = self.files

        @tool
        def save_file(path: str, content: str) -> str:
            """Save a source file to the project workspace."""
            files[path] = content
            return f"saved {path} ({len(content)} chars)"

        return save_file


# --------------------------------------------------------------------------- the crew
@dataclass
class CrewResult:
    outputs: dict[str, str]
    files: dict[str, str]
    qa: QAVerdict
    reworks: int


class SoftwareCrew:
    def __init__(self, llm_factory: Callable[[str], LLM] = llm_for, max_reworks: int = 1, verbose: bool | None = None):
        self.workspace = Workspace()
        self.pm = Role("pm", "Product Manager", "Turn a raw idea into crisp user stories with acceptance criteria",
                       "You ship small, testable increments.")
        self.architect = Role("architect", "Software Architect", "Design the simplest module layout and function signatures",
                              "You hate over-engineering.")
        self.developer = Role("developer", "Python Developer", "Implement the design as working Python code and save it with save_file",
                              "You write small, readable functions.", tools=[self.workspace.as_tool()])
        self.qa = Role("qa", "QA Reviewer", "Check the code against every acceptance criterion",
                       "You are skeptical and precise.")
        self.llm_factory = llm_factory
        self.max_reworks = max_reworks
        self.verbose = verbose
        self.tasks = [
            Task("stories", "Write user stories for: {idea}", "3-5 bullet user stories, each with acceptance criteria", self.pm),
            Task("design", "Design the implementation", "File list + function signatures + 1-line purpose each",
                 self.architect, context=["stories"]),
            Task("code", "Implement the design", "Call save_file for each file, then reply with a one-line summary",
                 self.developer, context=["stories", "design"]),
        ]

    def _agent(self, role: Role) -> Agent:
        return Agent(self.llm_factory(role.key), role.tools, role.system_prompt(), name=role.key,
                     tracer=Tracer(name=role.key, verbose=self.verbose))

    def _review(self, outputs: dict[str, str]) -> QAVerdict:
        code = "\n\n".join(f"# {p}\n{c}" for p, c in self.workspace.files.items()) or "(no files saved)"
        prompt = f"ACCEPTANCE CRITERIA:\n{outputs['stories']}\n\nCODE:\n{code}\n\nDoes the code satisfy every criterion?"
        return llm_json(self.llm_factory(self.qa.key), prompt, QAVerdict, system=self.qa.system_prompt())

    def kickoff(self, idea: str) -> CrewResult:
        inputs, outputs = {"idea": idea}, {}
        for task in self.tasks:  # sequential process: order fixed hai, koi manager nahi
            outputs[task.name] = self._agent(task.role).run(task.prompt(inputs, outputs)).output

        verdict, reworks = self._review(outputs), 0
        while not verdict.passed and reworks < self.max_reworks:  # feedback loop, budget ke saath
            reworks += 1
            fix = Task("code", "Fix the code. QA issues: " + "; ".join(verdict.issues),
                       "Call save_file with corrected files, then a one-line summary", self.developer, ["stories", "design"])
            outputs["code"] = self._agent(self.developer).run(fix.prompt(inputs, outputs)).output
            verdict = self._review(outputs)
        outputs["qa"] = verdict.model_dump_json()
        return CrewResult(outputs, dict(self.workspace.files), verdict, reworks)


# --------------------------------------------------------------------------- offline fake
def offline_llm(qa_fails_first: bool = True) -> ScriptedLLM:
    state = {"qa": 0, "dev_saved": 0}

    def respond(messages, tools):
        system = messages[0].content if messages[0].role == "system" else ""
        last = messages[-1]
        if "ROLE: Product Manager" in system:
            return "- As a user I can add two numbers. AC: add(2,3) == 5\n- As a user I get an error for non-numbers. AC: raises TypeError"
        if "ROLE: Software Architect" in system:
            return "calc.py: add(a: float, b: float) -> float  # adds numbers, raises TypeError on non-numbers"
        if "ROLE: Python Developer" in system:
            if last.role == "tool":
                return "Implemented calc.add."
            state["dev_saved"] += 1
            code = "def add(a, b):\n    return a + b\n"
            if state["dev_saved"] > 1:
                code = ("def add(a, b):\n    if not all(isinstance(x, (int, float)) for x in (a, b)):\n"
                        "        raise TypeError('numbers only')\n    return a + b\n")
            return tool_response(call("save_file", path="calc.py", content=code))
        if "ROLE: QA Reviewer" in system:
            state["qa"] += 1
            if qa_fails_first and state["qa"] == 1:
                return '{"passed": false, "issues": ["add() does not raise TypeError for non-numbers"]}'
            return '{"passed": true, "issues": []}'
        return "?"

    return ScriptedLLM(respond)
