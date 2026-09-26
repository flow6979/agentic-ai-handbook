**Language:** Hinglish · [English](TESTING.en.md)

# agentkit ko test aur tinker kaise karein

## Setup (ek baar, repo root se)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # ek provider ki key bharo (Groq/Gemini free tier theek hai)
```

## Offline tests (no key, no internet)

```bash
pytest common/tests -v
```

Yeh check karte hain:
- `@tool` se sahi JSON schema banta hai
- agent loop tool chalata hai aur result wapas bhejta hai
- tool error ya unknown tool pe crash nahi hota
- `max_steps` guard kaam karta hai
- retry (429 pe) aur fallback (401 pe agla provider)
- OpenAI aur Anthropic wire-format translation

## Real LLM ke saath 30-second check

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

Console mein `[agent:tool] add({'a': 1234, 'b': 5678})` aur phir final answer dikhna chahiye.

## Tinker karo

1. **Provider badlo:** `.env` mein `LLM_MODEL=gemini:gemini-2.5-flash` karo aur same script chalao. Code mein zero change.
2. **Fallback dekho:** `LLM_MODEL=openai:gpt-4o-mini,groq:llama-3.3-70b-versatile` rakho aur `OPENAI_API_KEY` galat daal do. Log mein "falling back" dikhega.
3. **Tool error:** `add` ke andar `raise ValueError("no negatives")` daalo jab `a < 0` ho, aur puchho "-5 + 3?". Dekho model error padh ke kya karta hai.
4. **Docstring ka asar:** tool ka docstring hata ke `"x"` kar do. Model tool kam ya galat use karega. Isi se samajh aata hai ki tool description kitna important hai.
5. **Trace file:** `AGENT_TRACE_FILE=traces.jsonl` set karo, run karo, phir `cat traces.jsonl`. Har step JSON mein milega.
6. **Naya provider jodo:** `llm/factory.py` ke `OPENAI_COMPAT` dict mein koi bhi OpenAI-compatible provider (e.g. Mistral: `https://api.mistral.ai/v1`) ek line mein add karo.
