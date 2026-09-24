"""ReAct style (a): classic TEXT-based Thought / Action / Observation loop.

Yeh original ReAct paper (Yao et al., 2022) wala tareeka hai. Model ko native tool
calling ki zaroorat nahi: hum prompt mein ek format sikhaate hain, model plain text
likhta hai, aur hum khud us text ko parse karke tool chalate hain.

    Thought: mujhe Everest ki height chahiye
    Action: lookup
    Action Input: {"query": "mount everest height"}
    Observation: <yeh hum likhte hain, model nahi>
    ...
    Final Answer: ...
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from agentkit import LLM, Message, NullTracer, Tool, Tracer, Usage

REACT_SYSTEM = """You answer questions by reasoning step by step and using tools.

Available tools:
{tool_desc}

Use EXACTLY this format, one step at a time:

Thought: <what you think and what to do next>
Action: <one tool name from [{tool_names}]>
Action Input: <JSON object with the tool arguments>

Then STOP and wait. The system will reply with:
Observation: <tool result>

Repeat Thought/Action/Observation as needed. When you know the answer write:

Thought: I now know the final answer
Final Answer: <the answer>
"""

_FINAL = re.compile(r"Final Answer:\s*(.*)", re.S)
_ACTION = re.compile(r"Action:\s*([\w\-]+)\s*\n\s*Action Input:\s*(.*)", re.S)


@dataclass
class ReActStep:
    thought: str
    action: str | None = None
    action_input: dict | None = None
    observation: str | None = None


@dataclass
class ReActResult:
    answer: str
    steps: list[ReActStep] = field(default_factory=list)
    llm_calls: int = 0
    usage: Usage = field(default_factory=Usage)
    stopped_reason: str = "final_answer"


def truncate_hallucinated_observation(text: str) -> str:
    """Models aksar 'Observation:' khud likh dete hain (fake result!). Wahin se kaat do.

    Real APIs mein yahi kaam `stop=["Observation:"]` stop-sequence karta hai.
    """
    idx = text.find("Observation:")
    return text[:idx].rstrip() if idx != -1 else text


def parse_step(text: str, tools: dict[str, Tool]) -> tuple:
    """Model ke text ko parse karo.

    Returns one of:
      ("final", answer, thought)
      ("action", tool_name, args_dict, thought)
      ("invalid", error_message, thought)
    """
    thought_m = re.search(r"Thought:\s*(.*?)(?:\n(?:Action|Final Answer):|$)", text, re.S)
    thought = thought_m.group(1).strip() if thought_m else ""

    # Action ko Final Answer se pehle check karo: agar dono hain to model confused hai,
    # lekin action pehle aaya hai toh wahi karo (ReAct ek step at a time).
    action_m = _ACTION.search(text)
    final_m = _FINAL.search(text)
    if final_m and (not action_m or final_m.start() < action_m.start()):
        return ("final", final_m.group(1).strip(), thought)
    if not action_m:
        return ("invalid", "Could not find 'Action:' + 'Action Input:' or 'Final Answer:'. Follow the format exactly.", thought)

    name, raw = action_m.group(1).strip(), action_m.group(2).strip().splitlines()[0].strip()
    if name not in tools:
        return ("invalid", f"Unknown tool {name!r}. Use one of {sorted(tools)}.", thought)
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        # Weak models aksar JSON ki jagah plain string dete hain. Single-arg tool ho to maaf kar do.
        params = list(tools[name].parameters["properties"])
        if len(params) != 1:
            return ("invalid", f"Action Input must be a JSON object with keys {params}.", thought)
        args = {params[0]: raw.strip('"\'')}
    return ("action", name, args, thought)


def run_react_text(llm: LLM, tools: list[Tool], question: str, *, max_steps: int = 8,
                   tracer: Tracer | None = None) -> ReActResult:
    tracer = tracer or NullTracer(name="react-text")
    tool_map = {t.name: t for t in tools}
    tool_desc = "\n".join(f"- {t.name}: {t.description} Args: {list(t.parameters['properties'])}" for t in tools)
    messages = [
        Message.system(REACT_SYSTEM.format(tool_desc=tool_desc, tool_names=", ".join(tool_map))),
        Message.user(f"Question: {question}"),
    ]
    result = ReActResult(answer="")

    for _ in range(max_steps):
        resp = llm.chat(messages)  # NOTE: tools param nahi bhej rahe: yeh pure text protocol hai
        result.llm_calls += 1
        result.usage = result.usage + resp.usage
        text = truncate_hallucinated_observation(resp.content or "")
        messages.append(Message.assistant(text))

        parsed = parse_step(text, tool_map)
        kind = parsed[0]
        if kind == "final":
            result.steps.append(ReActStep(thought=parsed[2]))
            result.answer = parsed[1]
            tracer.event("result", result.answer)
            return result
        if kind == "invalid":
            tracer.event("error", parsed[1])
            result.steps.append(ReActStep(thought=parsed[2], observation=f"FORMAT ERROR: {parsed[1]}"))
            messages.append(Message.user(f"Observation: FORMAT ERROR: {parsed[1]}"))
            continue

        _, name, args, thought = parsed
        tracer.event("llm", f"Thought: {thought}")
        tracer.event("tool", f"{name}({args})")
        try:
            obs = tool_map[name].run(args)
        except Exception as e:  # tool errors bhi observation hain: model inse seekhta hai
            obs = f"ERROR: {type(e).__name__}: {e}"
        tracer.event("tool", f"Observation: {obs}")
        result.steps.append(ReActStep(thought, name, args, obs))
        messages.append(Message.user(f"Observation: {obs}"))

    result.answer = "Stopped: step limit reached without a Final Answer."
    result.stopped_reason = "max_steps"
    return result
