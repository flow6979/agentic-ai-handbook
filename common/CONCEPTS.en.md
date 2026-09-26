**Language:** [Hinglish](CONCEPTS.md) · English

# agentkit: the small engine behind the whole repo

Every project in this repo is built on `agentkit`. It is a small (~600 lines), **framework-free** toolkit. The point is to keep LangChain/CrewAI-style "magic" out of the way, so the real code behind each concept stays visible.

## 1. What actually is an agent?

```
 Chatbot   : user ──► LLM ──► answer                  (one shot, no actions)
 Workflow  : user ──► step1 ──► step2 ──► answer      (CODE fixed the path)
 Agent     : user ──► LLM ⇄ tools (loop) ──► answer   (the LLM decides the path itself)
```

**Agent = LLM + Tools + Loop + (Memory) + (Guardrails)**

## 2. Layers

```
┌──────────────────────────────────────────────────────────┐
│  Your project (support agent, RAG bot, A2A server...)     │
├──────────────────────────────────────────────────────────┤
│  agent.py        Agent loop (max_steps, tool errors,     │
│                  human approval hook)                    │
│  tools.py        @tool: Python function ──► JSON schema  │
│  structured.py   llm_json: validated Pydantic output     │
│  embeddings.py   text ──► vector (for RAG)               │
│  tracing.py      log of every step (console + JSONL)     │
├──────────────────────────────────────────────────────────┤
│  llm/            PROVIDER ABSTRACTION                    │
│   base.py          LLM.chat(messages, tools) interface   │
│   types.py         Message, ToolCall, ToolSpec, Usage    │
│   openai_compat.py OpenAI, Groq, Gemini, Ollama,         │
│                    OpenRouter, DeepSeek, Together         │
│   anthropic.py     Claude (different wire format)        │
│   resilient.py     RetryingLLM, FallbackLLM              │
│   scripted.py      ScriptedLLM (tests, offline demos)    │
│   factory.py       get_llm("provider:model")             │
└──────────────────────────────────────────────────────────┘
          │ HTTP (httpx)
          ▼
   OpenAI / Anthropic / Gemini / Groq / Ollama (local) ...
```

## 3. How is multi-LLM possible? (The adapter pattern)

Every provider has a different format. We write code in one **neutral format** (`Message`, `ToolCall`), and each adapter translates it:

```
           neutral Message list
                   │
       ┌───────────┼─────────────────┐
       ▼           ▼                 ▼
 OpenAICompat   Anthropic        ScriptedLLM
  adapter        adapter         (fake, tests)
       │           │
 {"role":"tool",   {"role":"user","content":[
  "tool_call_id"}   {"type":"tool_result",...}]}
       │           │
   OpenAI/Groq/   Claude API
   Gemini/Ollama
```

Some real differences the adapters handle:

| Thing | OpenAI format | Anthropic format |
|---|---|---|
| System prompt | `role: system` inside `messages` | separate `system` field |
| Tool call | `message.tool_calls[].function.arguments` (JSON **string**) | a `tool_use` block in `content[]` (`input` = object) |
| Tool result | `role: tool` + `tool_call_id` | a `tool_result` block inside `role: user` |
| JSON mode | `response_format: json_object` | no flag; done through instructions |
| Tool schema key | `parameters` | `input_schema` |

Changing the model = only changing `LLM_MODEL` in `.env`, not the code.

## 4. The agent loop (agent.py)

```
 messages = [system, ...history, user]
        │
        ▼
 ┌──────────────┐
 │ llm.chat()   │◄──────────────────────────┐
 └──────┬───────┘                           │
        │                                   │
   any tool_calls?                          │
    ┌───┴────┐                              │
   No       Yes                             │
    │        │                              │
    ▼        ▼                              │
  return   for each call:                   │
  answer    • does the tool exist? (no → ERROR msg)
            • are the args valid JSON? (no → ERROR msg)
            • approve() hook?      (reject → ERROR msg)
            • tool.run()           (exception → ERROR msg)
            • result → Message.tool ─────────┘
                 (step > max_steps → stop)
```

**Key idea:** tool errors are not allowed to crash anything; instead they go back to the model as **text**. The model reads them and fixes things itself (passes different args or picks a different tool). This makes the agent quite robust.

## 5. @tool: from function to schema

```python
@tool
def get_weather(city: str, unit: Literal["c", "f"] = "c") -> str:
    """Get current weather for a city."""
```
automatically becomes:
```json
{"name": "get_weather", "description": "Get current weather for a city.",
 "parameters": {"type": "object",
   "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["c","f"]}},
   "required": ["city"]}}
```
The LLM decides when and how to call the tool just by looking at this schema. That is why **a good name and docstring = good tool use**.

## 6. Resilience

```
get_llm("groq:llama-3.3-70b-versatile,ollama:llama3.1")

 FallbackLLM
   ├── RetryingLLM(groq)    429/5xx/timeout? → 1s, 2s, 4s backoff → still failing?
   └── RetryingLLM(ollama)  ← fall back here
```

- **Retryable:** 429 (rate limit), 5xx, network timeout
- **Non-retryable:** 400 (bad request), 401 (bad key). Retrying these is pointless; fail straight away or fall back.

## 7. ScriptedLLM: how to test agents

LLMs are non-deterministic and cost money, so unit tests use a **fake LLM**:

```python
llm = ScriptedLLM([tool_response(call("add", a=2, b=3)), "Answer is 5"])
```

With this we test *our* code: the loop, parsing, routing and error handling. The LLM's quality is checked separately with **evals** (live runs, golden datasets); we will see that in `01-production-agent`.

## 8. structured.py: validated JSON

```
prompt + JSON schema ──► LLM ──► extract_json ──► Pydantic validate
                           ▲                            │ fail
                           └──── "this was wrong: <error>" ◄┘  (self-correction retry)
```

Wherever **code** consumes the LLM's output (a router decision, a plan, a score), this is used instead of free text.
