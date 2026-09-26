**Language:** Hinglish · [English](TESTING.en.md)

# 02 · Agent-as-Tool: Test aur tinker kaise karein

## Offline run

```bash
python 05-agent-communication/02-agent-as-tool/main.py --offline
```

stderr pe teen tracers dikhenge: `[manager:tool]`, `[math_expert:tool]`, `[copywriter:result]`.
Dhyan do ki **manager ke tool call ke andar** math_expert ka poora loop chal raha hai.

Last mein "WHAT THE MANAGER SAW" section dikhata hai ki manager ko sirf JSON envelope mila,
specialist ki andar ki chat nahi.

## Real LLM

```bash
python 05-agent-communication/02-agent-as-tool/main.py "Revenue was 4.2 lakh last month and 5.1 lakh this month. Growth %? Write a LinkedIn post."
```

Dekho:
- kya manager ne task self-contained likha? (`[manager:tool] ask_math_expert({'task': ...})`)
- kya math_expert ne khud calculate kiya ya tool use kiya?
- copywriter ne valid JSON diya ya nahi? (nahi diya to `output` string reh jayega)

## Tests

```bash
pytest 05-agent-communication/02-agent-as-tool -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_manager_delegates_and_gets_structured_results` | delegation, JSON envelope, aur **context isolation** (`SECRET-ID-42` specialist tak nahi pahuncha) |
| `test_subagent_failure_is_contained` | sub-agent max_steps pe ruke to `ok: false` |
| `test_subagent_exception_is_contained` | provider down ho to error JSON, crash nahi |
| `test_calculator_is_safe` | LLM input pe code execution nahi hota |

## Tinker karo

1. **Sasta specialist:** `main.py` mein math_expert ke liye alag model do
   (`get_llm("groq:llama-3.1-8b-instant")`) aur manager ke liye bada. Cost/quality compare karo.
2. **Teesra specialist:** `researcher` agent add karo (section 03 ka web search tool use karke)
   aur `ask_researcher` tool manager ko do.
3. **Isolation todo:** `agent_as_tool` mein task ke saath manager ki history bhi bhejo. Tokens
   (`tokens` field) kitne badhe? Kya answer better hua?
4. **Parallel:** manager ke ek response mein 2 tool calls ho to abhi sequential chalte hain.
   `concurrent.futures.ThreadPoolExecutor` se parallel karo (Agent loop copy karke).
5. **Output budget:** specialist ka output 300 chars se lamba ho to truncate karo aur `truncated: true`
   add karo. Manager ka context bachane ke liye yeh real trick hai.
