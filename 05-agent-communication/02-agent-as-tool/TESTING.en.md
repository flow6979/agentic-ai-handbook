**Language:** [Hinglish](TESTING.md) · English

# 02 · Agent-as-Tool: how to test and tinker

## Offline run

```bash
python 05-agent-communication/02-agent-as-tool/main.py --offline
```

You will see three tracers on stderr: `[manager:tool]`, `[math_expert:tool]`, `[copywriter:result]`.
Notice that math_expert's whole loop runs **inside the manager's tool call**.

At the end, the "WHAT THE MANAGER SAW" section shows that the manager received only the JSON envelope,
not the specialist's internal chat.

## Real LLM

```bash
python 05-agent-communication/02-agent-as-tool/main.py "Revenue was 4.2 lakh last month and 5.1 lakh this month. Growth %? Write a LinkedIn post."
```

Check:
- did the manager write a self-contained task? (`[manager:tool] ask_math_expert({'task': ...})`)
- did math_expert calculate it itself or use a tool?
- did the copywriter return valid JSON? (if not, `output` stays a string)

## Tests

```bash
pytest 05-agent-communication/02-agent-as-tool -v
```

| Test | What it proves |
|---|---|
| `test_manager_delegates_and_gets_structured_results` | delegation, the JSON envelope, and **context isolation** (`SECRET-ID-42` never reached the specialist) |
| `test_subagent_failure_is_contained` | a sub-agent stopping at max_steps gives `ok: false` |
| `test_subagent_exception_is_contained` | a provider outage gives an error JSON, not a crash |
| `test_calculator_is_safe` | LLM input never leads to code execution |

## Tinker with it

1. **Cheap specialist:** in `main.py`, give math_expert a different model
   (`get_llm("groq:llama-3.1-8b-instant")`) and the manager a bigger one. Compare cost/quality.
2. **Third specialist:** add a `researcher` agent (using the web search tool from section 03)
   and give the manager an `ask_researcher` tool.
3. **Break isolation:** in `agent_as_tool`, send the manager's history along with the task. How much did
   the tokens (`tokens` field) grow? Did the answer get better?
4. **Parallel:** if one manager response contains 2 tool calls, they currently run sequentially.
   Make them parallel with `concurrent.futures.ThreadPoolExecutor` (copy the Agent loop).
5. **Output budget:** if a specialist's output is longer than 300 chars, truncate it and add `truncated: true`.
   This is a real trick for protecting the manager's context.
