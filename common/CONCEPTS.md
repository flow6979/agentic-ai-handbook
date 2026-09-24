# agentkit: poore repo ka chhota sa engine

Is repo ka har project `agentkit` pe bana hai. Yeh ek chhota (~600 lines), **framework-free** toolkit hai. Iska maksad hai ki LangChain/CrewAI jaisa "magic" beech mein na aaye, aur har concept ka asli code saaf dikhe.

## 1. Agent asal mein hai kya?

```
 Chatbot   : user ──► LLM ──► answer                  (ek shot, koi action nahi)
 Workflow  : user ──► step1 ──► step2 ──► answer      (raasta CODE ne fix kiya)
 Agent     : user ──► LLM ⇄ tools (loop) ──► answer   (raasta LLM khud decide karta hai)
```

**Agent = LLM + Tools + Loop + (Memory) + (Guardrails)**

## 2. Layers

```
┌──────────────────────────────────────────────────────────┐
│  Tumhara project (support agent, RAG bot, A2A server...)  │
├──────────────────────────────────────────────────────────┤
│  agent.py        Agent loop (max_steps, tool errors,     │
│                  human approval hook)                    │
│  tools.py        @tool: Python function ──► JSON schema  │
│  structured.py   llm_json: validated Pydantic output     │
│  embeddings.py   text ──► vector (RAG ke liye)           │
│  tracing.py      har step ka log (console + JSONL)       │
├──────────────────────────────────────────────────────────┤
│  llm/            PROVIDER ABSTRACTION                    │
│   base.py          LLM.chat(messages, tools) interface   │
│   types.py         Message, ToolCall, ToolSpec, Usage    │
│   openai_compat.py OpenAI, Groq, Gemini, Ollama,         │
│                    OpenRouter, DeepSeek, Together         │
│   anthropic.py     Claude (alag wire format)             │
│   resilient.py     RetryingLLM, FallbackLLM              │
│   scripted.py      ScriptedLLM (tests, offline demos)    │
│   factory.py       get_llm("provider:model")             │
└──────────────────────────────────────────────────────────┘
          │ HTTP (httpx)
          ▼
   OpenAI / Anthropic / Gemini / Groq / Ollama (local) ...
```

## 3. Multi-LLM kaise possible hai? (Adapter pattern)

Har provider ka format alag hai. Hum ek **neutral format** (`Message`, `ToolCall`) mein code likhte hain, aur har adapter use translate karta hai:

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

Kuch real differences jo adapters sambhaalte hain:

| Cheez | OpenAI format | Anthropic format |
|---|---|---|
| System prompt | `messages` mein `role: system` | alag `system` field |
| Tool call | `message.tool_calls[].function.arguments` (JSON **string**) | `content[]` mein `tool_use` block (`input` = object) |
| Tool result | `role: tool` + `tool_call_id` | `role: user` ke andar `tool_result` block |
| JSON mode | `response_format: json_object` | flag nahi hai, instruction se karwate hain |
| Tool schema key | `parameters` | `input_schema` |

Model badalna = sirf `.env` mein `LLM_MODEL` change karna, code nahi.

## 4. Agent loop (agent.py)

```
 messages = [system, ...history, user]
        │
        ▼
 ┌──────────────┐
 │ llm.chat()   │◄──────────────────────────┐
 └──────┬───────┘                           │
        │                                   │
   tool_calls hain?                         │
    ┌───┴────┐                              │
   Nahi     Haan                            │
    │        │                              │
    ▼        ▼                              │
  return   har call ke liye:                │
  answer    • tool exist karta hai? (nahi → ERROR msg)
            • args valid JSON?     (nahi → ERROR msg)
            • approve() hook?      (reject → ERROR msg)
            • tool.run()           (exception → ERROR msg)
            • result → Message.tool ─────────┘
                 (step > max_steps → ruk jao)
```

**Key idea:** tool ki errors ko crash nahi hone dete, balki model ko **text** mein wapas bhejte hain. Model padh ke khud sudhaarta hai (dusre args deta hai ya dusra tool chunta hai). Isse agent kaafi robust ho jata hai.

## 5. @tool: function se schema

```python
@tool
def get_weather(city: str, unit: Literal["c", "f"] = "c") -> str:
    """Get current weather for a city."""
```
yeh automatically ban jata hai:
```json
{"name": "get_weather", "description": "Get current weather for a city.",
 "parameters": {"type": "object",
   "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["c","f"]}},
   "required": ["city"]}}
```
LLM sirf yeh schema dekh ke decide karta hai ki tool kab aur kaise chalana hai. Isliye **achha naam aur docstring = achha tool use**.

## 6. Resilience

```
get_llm("groq:llama-3.3-70b-versatile,ollama:llama3.1")

 FallbackLLM
   ├── RetryingLLM(groq)    429/5xx/timeout? → 1s, 2s, 4s backoff → phir bhi fail?
   └── RetryingLLM(ollama)  ← yahan gir jao
```

- **Retryable:** 429 (rate limit), 5xx, network timeout
- **Non-retryable:** 400 (bad request), 401 (bad key). Inhe retry karna bekaar hai, seedha fail ya fallback.

## 7. ScriptedLLM: agents ko test kaise karein

LLM non-deterministic hai aur paise lagte hain, isliye unit tests mein **fake LLM** use karte hain:

```python
llm = ScriptedLLM([tool_response(call("add", a=2, b=3)), "Answer is 5"])
```

Isse hum *apna* code test karte hain: loop, parsing, routing aur error handling. LLM ki quality alag se **evals** (live runs, golden datasets) se check hoti hai; woh `01-production-agent` mein dekhenge.

## 8. structured.py: validated JSON

```
prompt + JSON schema ──► LLM ──► extract_json ──► Pydantic validate
                           ▲                            │ fail
                           └──── "yeh galat tha: <error>" ◄┘  (self-correction retry)
```

Jahan bhi LLM ka output **code** consume karta hai (router decision, plan, score), wahan free text ki jagah yahi use hota hai.
