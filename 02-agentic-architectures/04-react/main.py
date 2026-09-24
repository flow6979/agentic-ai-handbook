"""ReAct demo: same question, do styles, side by side.

    python 02-agentic-architectures/04-react/main.py "How many times taller is Everest than the Eiffel Tower?"
    python 02-agentic-architectures/04-react/main.py --style text "..."
    python 02-agentic-architectures/04-react/main.py --offline
"""
from __future__ import annotations

import argparse

from agentkit import ScriptedLLM, Tracer, call, get_llm, tool_response

from react_native import run_react_native
from react_textloop import run_react_text
from react_tools import TOOLS

DEFAULT_Q = "How many times taller is Mount Everest than the Eiffel Tower?"


def offline_llms() -> tuple[ScriptedLLM, ScriptedLLM]:
    text_llm = ScriptedLLM([
        'Thought: I need the height of Mount Everest.\nAction: lookup\nAction Input: {"query": "mount everest height"}',
        # Model ne fake Observation bhi likh diya: hum use truncate kar denge
        'Thought: Now the Eiffel Tower height.\nAction: lookup\nAction Input: {"query": "eiffel tower height"}\n'
        "Observation: 300 metres (hallucinated!)",
        'Thought: Divide 8849 by 330.\nAction: calculator\nAction Input: {"expression": "8849 / 330"}',
        "Thought: I now know the final answer\nFinal Answer: Mount Everest is about 26.8 times taller than the Eiffel Tower.",
    ])
    native_llm = ScriptedLLM([
        tool_response(call("lookup", query="mount everest height"), call("lookup", query="eiffel tower height")),
        tool_response(call("calculator", expression="8849 / 330")),
        "Mount Everest is about 26.8 times taller than the Eiffel Tower (8849 m vs 330 m).",
    ])
    return text_llm, native_llm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default=DEFAULT_Q)
    ap.add_argument("--style", choices=["text", "native", "both"], default="both")
    ap.add_argument("--offline", action="store_true", help="use a scripted fake LLM (no API key)")
    args = ap.parse_args()

    if args.offline:
        text_llm, native_llm = offline_llms()
        args.question = DEFAULT_Q
    else:
        text_llm = native_llm = get_llm()

    if args.style in ("text", "both"):
        print("\n=== (a) Text-based ReAct (Thought/Action/Observation parsing) ===")
        r = run_react_text(text_llm, TOOLS, args.question, tracer=Tracer(name="react-text"))
        print(f"\nANSWER: {r.answer}\nllm_calls={r.llm_calls} tokens={r.usage.input_tokens}+{r.usage.output_tokens}")

    if args.style in ("native", "both"):
        print("\n=== (b) Native function calling (agentkit.Agent) ===")
        r2 = run_react_native(native_llm, args.question, tracer=Tracer(name="react-native"))
        print(f"\nANSWER: {r2.output}\nllm_calls={r2.steps} tokens={r2.usage.input_tokens}+{r2.usage.output_tokens}")


if __name__ == "__main__":
    main()
