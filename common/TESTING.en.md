**Language:** [Hinglish](TESTING.md) · English

# How to test and tinker with agentkit

## Setup (once, from the repo root)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # fill in one provider's key (Groq/Gemini free tier is fine)
```

## Offline tests (no key, no internet)

```bash
pytest common/tests -v
```

These check that:
- `@tool` produces the correct JSON schema
- the agent loop runs the tool and sends the result back
- a tool error or an unknown tool does not crash anything
- the `max_steps` guard works
- retry (on 429) and fallback (to the next provider on 401)
- OpenAI and Anthropic wire-format translation

## A 30-second check with a real LLM

```bash
python - <<'EOF'
from agentkit import Agent, tool, get_llm

@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

agent = Agent(get_llm(), [add])
print(agent.run("What is 1234 + 5678? Use the tool.").output)
EOF
```

In the console you should see `[agent:tool] add({'a': 1234, 'b': 5678})` and then the final answer.

## Tinker

1. **Switch providers:** set `LLM_MODEL=gemini:gemini-3.8-flash` in `.env` and run the same script. Zero code changes.
2. **Watch the fallback:** set `LLM_MODEL=openai:gpt-4o-mini,groq:llama-3.3-70b-versatile` and put a wrong `OPENAI_API_KEY`. You will see "falling back" in the log.
3. **Tool error:** inside `add`, `raise ValueError("no negatives")` when `a < 0`, and ask "-5 + 3?". Watch what the model does after reading the error.
4. **Effect of the docstring:** change the tool's docstring to just `"x"`. The model will use the tool less, or wrongly. This shows how important the tool description is.
5. **Trace file:** set `AGENT_TRACE_FILE=traces.jsonl`, run it, then `cat traces.jsonl`. You get every step as JSON.
6. **Add a new provider:** add any OpenAI-compatible provider (for example Mistral: `https://api.mistral.ai/v1`) in one line to the `OPENAI_COMPAT` dict in `llm/factory.py`.
