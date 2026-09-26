**Language:** Hinglish · [English](README.en.md)

# lab-api: handbook ko website se chalao

Yeh folder handbook aur [Agent Lab website](https://flow6979.github.io/agent-lab/) ([code](https://github.com/flow6979/agent-lab)) ke beech ka pul hai. Website tumhare browser ke andar **Pyodide** (Python in WebAssembly) chalati hai, aur yahi `labapi` package usme load hota hai.

```
 Website (React)  ──request──►  Web Worker (Pyodide)  ──►  labapi.run(request, emit)
                  ◄──events───                              │
                                                            ├─ ping_lab.py   -> LLM connection test
                                                            ├─ react_lab.py  -> 02-agentic-architectures/04-react
                                                            ├─ rag_lab.py    -> 04-rag/02-pdf-chat
                                                            ├─ ... (har *_lab.py khud register hota hai)
                                                            ▼
                                                     asli project code + agentkit
```

## Request aur response

```python
from labapi import run

run({
    "lab": "react",
    "params": {"mode": "native", "question": "How many times taller is Everest than the Eiffel Tower?"},
    "llm": {"spec": "groq:llama-3.3-70b-versatile", "keys": {"groq": "gsk_..."}},
    "offline": False,
}, emit=print)
# -> {"ok": True, "result": {"answer": "...", "llm_calls": 3, "input_tokens": ..., "ms": ...}}
# ya {"ok": False, "error": {"kind": "auth", "status": 401, "message": "..."}}
```

`emit` ko har step ka event milta hai (`type`: `step`, `llm_call`, `trace`, `error`). Website inhi se live trace banati hai.

## Browser ke liye agentkit mein kya badla

| Badlav | File | Kyun |
|---|---|---|
| HTTP layer: normal Python mein `httpx`, browser mein synchronous `XMLHttpRequest` | `common/agentkit/llm/http.py` | Pyodide mein sockets nahi hote; Web Worker mein sync XHR allowed hai, isliye sync agent code bina badle chalta hai |
| `get_llm(spec, api_keys={...})` aur `get_embedder(spec, api_key=...)` | `factory.py`, `embeddings.py` | Key env se nahi, user ki request se aati hai (kahin save nahi hoti) |
| `Tracer(on_event=...)` | `tracing.py` | Har step turant UI ko bhejna |
| Claude ke liye `anthropic-dangerous-direct-browser-access` header (sirf browser mein) | `anthropic.py` | Anthropic ka browser opt-in |

## Naya lab jodna

1. `labapi/<name>_lab.py` banao aur usme `LAB = Lab(id=..., project=..., run=..., defaults=..., pip=[...], smoke_cases=[...])` likho. `react_lab.py` reference hai.
2. `run(ctx)` mein:
   - `use_project("<folder>")` se project import karo;
   - LLM ke liye `ctx.llm()` (ya role ke liye `ctx.llm("writer")`);
   - UI events ke liye `ctx.step(kind, text, ...)`;
   - `ctx.offline` pe `ScriptedLLM` chalao.
3. Test likho (`test_<name>_lab.py`) aur `pytest lab-api` chalao.
4. Website repo mein `npm run smoke` chalao: yeh har `smoke_cases` ko asli Pyodide mein offline chalata hai. Deploy bhi isi check ke baad hota hai.

## Browser ki limits

- Sirf CORS allow karne wale hosts: LLM providers, Wikipedia, open-meteo, Tavily.
- Threads, subprocess aur servers nahi chalte, isliye MCP/A2A lab recorded replay hai.
- Offline mode har lab ke liye zaroori hai.

## Test

```bash
pytest lab-api -v
```
