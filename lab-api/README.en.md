**Language:** [Hinglish](README.md) · English

# lab-api: run the handbook from the website

This folder is the bridge between the handbook and the [Agent Lab website](https://flow6979.github.io/agent-lab/) ([code](https://github.com/flow6979/agent-lab)). The website runs **Pyodide** (Python in WebAssembly) inside your browser and loads this `labapi` package into it.

```
 Website (React)  ──request──►  Web Worker (Pyodide)  ──►  labapi.run(request, emit)
                  ◄──events───                              │
                                                            ├─ ping_lab.py   -> LLM connection test
                                                            ├─ react_lab.py  -> 02-agentic-architectures/04-react
                                                            ├─ rag_lab.py    -> 04-rag/02-pdf-chat
                                                            ├─ ... (every *_lab.py registers itself)
                                                            ▼
                                                     real project code + agentkit
```

## Request and response

```python
from labapi import run

run({
    "lab": "react",
    "params": {"mode": "native", "question": "How many times taller is Everest than the Eiffel Tower?"},
    "llm": {"spec": "groq:llama-3.3-70b-versatile", "keys": {"groq": "gsk_..."}},
    "offline": False,
}, emit=print)
# -> {"ok": True, "result": {"answer": "...", "llm_calls": 3, "input_tokens": ..., "ms": ...}}
# or {"ok": False, "error": {"kind": "auth", "status": 401, "message": "..."}}
```

`emit` receives an event for every step (`type`: `step`, `llm_call`, `trace`, `error`). The website builds its live trace from these.

## What changed in agentkit for the browser

| Change | File | Why |
|---|---|---|
| HTTP layer: `httpx` in normal Python, synchronous `XMLHttpRequest` in the browser | `common/agentkit/llm/http.py` | Pyodide has no sockets; sync XHR is allowed inside a Web Worker, so the sync agent code runs unchanged |
| `get_llm(spec, api_keys={...})` and `get_embedder(spec, api_key=...)` | `factory.py`, `embeddings.py` | The key comes from the user's request, not the environment (never stored) |
| `Tracer(on_event=...)` | `tracing.py` | Send every step to the UI immediately |
| The `anthropic-dangerous-direct-browser-access` header for Claude (browser only) | `anthropic.py` | Anthropic's browser opt-in |

## Adding a lab

1. Create `labapi/<name>_lab.py` with `LAB = Lab(id=..., project=..., run=..., defaults=..., pip=[...], smoke_cases=[...])`. `react_lab.py` is the reference.
2. In `run(ctx)`:
   - import the project with `use_project("<folder>")`;
   - use `ctx.llm()` for the LLM (or `ctx.llm("writer")` for a role);
   - emit UI events with `ctx.step(kind, text, ...)`;
   - use a `ScriptedLLM` when `ctx.offline` is set.
3. Write a test (`test_<name>_lab.py`) and run `pytest lab-api`.
4. In the website repo, run `npm run smoke`: it runs every `smoke_cases` entry offline inside real Pyodide. Deploys only happen after this check.

## Browser limits

- Only CORS-enabled hosts work: LLM providers, Wikipedia, open-meteo, Tavily.
- Threads, subprocesses and servers do not run, so the MCP/A2A lab is a recorded replay.
- Offline mode is required for every lab.

## Test

```bash
pytest lab-api -v
```
