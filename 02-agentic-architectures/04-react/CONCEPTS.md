**Language:** Hinglish · [English](CONCEPTS.en.md)

# ReAct: Reason + Act

## 1. Problem kya hai?

LLM akela sirf "sochta" hai (text generate karta hai). Usko facts nahi pata (ya galat pata hain),
aur arithmetic mein galti karta hai. Doosri taraf, sirf tools chalana bina soche bhi bekaar hai.

**ReAct** (Yao et al., 2022) dono ko mix karta hai: model ek step sochta hai (Reason), phir ek
action leta hai (Act), phir result dekhta hai (Observe), aur yeh loop chalta rehta hai jab tak
answer na mil jaye.

```
            ┌───────────────────────────────┐
            │  Question                     │
            └───────────────┬───────────────┘
                            ▼
                 ┌─────────────────────┐
         ┌─────► │ Thought (reason)    │  "mujhe Everest ki height chahiye"
         │       └──────────┬──────────┘
         │                  ▼
         │       ┌─────────────────────┐
         │       │ Action (tool call)  │  lookup("mount everest height")
         │       └──────────┬──────────┘
         │                  ▼
         │       ┌─────────────────────┐
         └────── │ Observation         │  "8849 metres"
      (repeat)   └──────────┬──────────┘
                            │ jab kaafi info mil gayi
                            ▼
                 ┌─────────────────────┐
                 │ Final Answer        │
                 └─────────────────────┘
```

Key idea: **har step ka observation agle thought ko ground karta hai**. Isliye hallucination
kam hoti hai, aur reasoning trace dikhta hai (debugging mein bahut kaam aata hai).

## 2. ReAct ke do implementation styles

### (a) Text-based ReAct (original paper wala)

Model ko prompt mein ek *format* sikhaate hain. Model plain text likhta hai, hum regex se parse
karte hain.

```
Model likhta hai:                         Hum (code) karte hain:
─────────────────                         ──────────────────────
Thought: Everest height chahiye
Action: lookup                    ───►    parse_step() → ("action", "lookup", {...})
Action Input: {"query": "..."}            tool chalao
                                  ◄───    "Observation: 8849 metres" message append
Thought: ab divide karo
...
Final Answer: ~26.8x              ───►    parse_step() → ("final", "...")  → return
```

**Kab use karein:** jab model native tool calling support nahi karta (chhote open-source
models, purane models, raw completion APIs), ya jab tumhe protocol pe pura control chahiye.

**Pitfalls (yeh sab code mein handle kiye hain):**

| Problem | Kya hota hai | Fix |
|---|---|---|
| Hallucinated observation | Model `Observation: 300m` khud likh deta hai | `truncate_hallucinated_observation()`, API mein `stop=["Observation:"]` |
| Format tootna | Model format bhool jata hai | `FORMAT ERROR` observation wapas bhejo, model khud sudhar leta hai |
| JSON ki jagah string | `Action Input: eiffel tower` | Single-arg tool ho to string accept kar lo |
| Unknown tool | `Action: google` | Error observation me available tools batao |
| Infinite loop | Model kabhi Final Answer nahi deta | `max_steps` |

### (b) Native function calling

Modern APIs (OpenAI, Anthropic, Gemini, Groq...) mein model **structured `tool_calls`** return
karta hai. Parsing provider karta hai, hum nahi. Loop same hai.

```
 messages + tool schemas ──► LLM ──► {tool_calls: [{name: "lookup", arguments: {...}}]}
                                          │
             tool result (role="tool") ◄──┘
                     │
                     └──► LLM ──► ... ──► plain text = final answer
```

Bonus: ek hi turn mein **parallel tool calls** (dono lookups ek saath), jo text style mein
mushkil hai.

### Comparison

| | Text ReAct | Native function calling |
|---|---|---|
| Model requirement | Koi bhi text model | Tool-calling wala model |
| Parsing | Hum (regex, fragile) | Provider (robust JSON) |
| Explicit "Thought" | Hamesha dikhta hai | Optional (model chahe to text ke saath) |
| Parallel calls | Mushkil | Built-in |
| Tokens | Zyada (format instructions + scratchpad) | Kam |
| Production default | Fallback | **Yahi use karo** |

## 3. Variants / subtypes

- **Zero-shot ReAct:** sirf format instructions (yahi project).
- **Few-shot ReAct:** prompt mein 1-3 solved examples: weak models ke liye accuracy badhti hai.
- **ReAct + reflection:** fail hone pe self-critique (dekho `06-reflection`).
- **ReAct with parallel tools:** native style mein ek step mein multiple calls.
- **ReAct vs Plan-and-Execute vs ReWOO:** ReAct har step pe LLM call karta hai (adaptive, lekin
  mehnga). ReWOO pehle hi saare calls plan karta hai (sasta, lekin kam adaptive). Dekho `05` aur `09`.

## 4. Kab use karein, kab nahi

**Use karo:** open-ended tasks jahan next step pichle result pe depend karta hai (research,
debugging, customer support lookups).

**Mat use karo:** fixed steps wale tasks (prompt chaining sasta aur predictable hai), ya jab
latency bahut critical ho (har step = ek LLM round trip).

## 5. Production pitfalls

- **Tool output ko untrusted maano:** calculator mein `eval()` nahi, AST-based `safe_eval()`.
  Tool results mein prompt injection bhi aa sakta hai ("ignore previous instructions...").
- **Context growth:** har step pe messages badhte hain → tokens aur cost badhti hai. Lambe tool
  outputs truncate/summarize karo.
- **Step limit + timeout** dono rakho.
- **Trace log karo:** thought/action/observation se hi pata chalta hai agent kahan bhatka.

## 6. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Tools (safe calculator, KB lookup) | `react_tools.py` → `safe_eval`, `calculator`, `lookup` |
| Text ReAct prompt/format | `react_textloop.py` → `REACT_SYSTEM` |
| Output parsing | `react_textloop.py` → `parse_step()` |
| Hallucinated observation fix | `react_textloop.py` → `truncate_hallucinated_observation()` |
| Loop + format-error recovery + max_steps | `react_textloop.py` → `run_react_text()` |
| Native function calling | `react_native.py` → `build_native_agent()` (agentkit `Agent`) |
| Side-by-side comparison | `main.py` (prints llm_calls + tokens for both) |

Offline demo mein notice karo: native style ne 3 LLM calls kiye (dono lookups parallel), text
style ne 4, aur text style ke tokens kaafi zyada hain (format instructions + scratchpad).
