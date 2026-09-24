"""Agent-as-Tool: ek poore Agent ko dusre agent ke liye ek 'function' bana do.

Manager agent ko lagta hai woh bas ek tool call kar raha hai:
    ask_math_expert(task="...")
Lekin andar ek poora sub-agent chalta hai, apne tools aur apne loop ke saath.

Teen important cheezein:
1. Context isolation: sub-agent ko sirf `task` milta hai, manager ki poori chat nahi.
   -> kam tokens, focused kaam, manager ke secrets leak nahi hote.
2. Structured result: sub-agent ka output JSON envelope mein wapas jata hai
   (agent, ok, output, steps, tokens), taaki manager reliably padh sake.
3. Failure contained: sub-agent fail/max_steps ho jaye to error result, crash nahi.
"""
from __future__ import annotations

import json

from agentkit import Agent, extract_json
from agentkit.tools import Tool


def agent_as_tool(agent: Agent, name: str, description: str, *, expect_json: bool = False) -> Tool:
    def run(task: str) -> str:
        try:
            res = agent.run(task)  # fresh context: sirf task string
        except Exception as e:
            return json.dumps({"agent": agent.name, "ok": False, "error": f"{type(e).__name__}: {e}"})
        output: object = res.output
        if expect_json:
            try:
                output = extract_json(res.output)
            except ValueError:
                pass  # model ne JSON nahi diya; text hi bhej do, manager samajh lega
        return json.dumps(
            {
                "agent": agent.name,
                "ok": res.stopped_reason == "final_answer",
                "output": output,
                "steps": res.steps,
                "tokens": res.usage.input_tokens + res.usage.output_tokens,
            },
            ensure_ascii=False,
        )

    return Tool(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Self-contained task for the specialist. Include all needed facts."}},
            "required": ["task"],
        },
        fn=run,
    )
