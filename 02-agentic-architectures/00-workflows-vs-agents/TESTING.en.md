**Language:** [Hinglish](TESTING.md) · English

# Testing: workflows vs agents demo

## Setup (from the repo root, once)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # fill in one provider's key, e.g. LLM_MODEL=groq:llama-3.3-70b-versatile
```

## Run

```bash
# without a key (scripted fake LLM):
python 02-agentic-architectures/00-workflows-vs-agents/main.py --offline

# with a real LLM:
python 02-agentic-architectures/00-workflows-vs-agents/main.py
python 02-agentic-architectures/00-workflows-vs-agents/main.py --user u2
```

## What to look for

```
=== 1) WORKFLOW ===
{'subtotal': 4097.0, 'tax': 737.46, 'total': 4834.46}   <- computed by code
...
LLM calls: 1

=== 2) AGENT ===
[cart-agent:tool] get_cart({'user_id': 'u1'})           <- the LLM picked the tool itself
[cart-agent:tool] compute_total({'subtotal': 4097.0})
...
LLM calls: 3  tokens: Usage(...)
```

- In the workflow, the total will **always** be the same and correct.
- In agent mode (real LLM), check: did the model call `compute_total`, or did it do the math itself? The system prompt forbids it, but models sometimes ignore that. This is what "low predictability" means.
- Compare the token counts: the agent re-sends the full history on every step.

## Offline tests

```bash
pytest 02-agentic-architectures/00-workflows-vs-agents -v
```

- `test_chain_does_math_in_code_and_calls_llm_once`: chain = 1 LLM call, and the numbers were passed in the prompt.
- `test_agent_decides_tool_order_itself`: the agent chose the `get_cart` -> `compute_total` order.
- `test_agent_recovers_from_bad_user_id`: a tool error does not crash, it goes back to the model.

## Tinker with it

1. **A new question**: ask the agent *"What is the combined total of the carts of u1 and u2?"*. The chain cannot do this without code changes; the agent can. That is flexibility.
2. **Add a coupon tool**: create an `apply_coupon(code) -> discount%` tool. The chain needs a new step written in code; for the agent, just add it to the tools list. Compare the code diff of both.
3. **Remove the system prompt**: delete the "Never do tax math yourself" line and run 5 times with a real LLM. How many times did the model do the (wrong?) math itself?
4. **Set max_steps=1** on the agent: what happens? (look at `stopped_reason`)
5. **Measure cost**: set `AGENT_TRACE_FILE=trace.jsonl`, run both, and compare tokens.
