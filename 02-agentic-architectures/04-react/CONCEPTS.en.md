**Language:** [Hinglish](CONCEPTS.md) · English

# ReAct: Reason + Act

## 1. What is the problem?

On its own, an LLM only "thinks" (generates text). It doesn't know facts (or knows them wrong),
and it makes arithmetic mistakes. On the other hand, running tools without thinking is useless too.

**ReAct** (Yao et al., 2022) mixes the two: the model thinks one step (Reason), then takes an
action (Act), then looks at the result (Observe), and this loop keeps going until it
finds the answer.

```
            ┌───────────────────────────────┐
            │  Question                     │
            └───────────────┬───────────────┘
                            ▼
                 ┌─────────────────────┐
         ┌─────► │ Thought (reason)    │  "I need Everest's height"
         │       └──────────┬──────────┘
         │                  ▼
         │       ┌─────────────────────┐
         │       │ Action (tool call)  │  lookup("mount everest height")
         │       └──────────┬──────────┘
         │                  ▼
         │       ┌─────────────────────┐
         └────── │ Observation         │  "8849 metres"
      (repeat)   └──────────┬──────────┘
                            │ once it has enough info
                            ▼
                 ┌─────────────────────┐
                 │ Final Answer        │
                 └─────────────────────┘
```

Key idea: **each step's observation grounds the next thought**. That is why hallucination
goes down, and the reasoning trace is visible (very useful for debugging).

## 2. Two implementation styles of ReAct

### (a) Text-based ReAct (the original paper's version)

We teach the model a *format* in the prompt. The model writes plain text, and we parse it
with a regex.

```
The model writes:                         We (code) do:
─────────────────                         ─────────────
Thought: I need Everest's height
Action: lookup                    ───►    parse_step() → ("action", "lookup", {...})
Action Input: {"query": "..."}            run the tool
                                  ◄───    append the "Observation: 8849 metres" message
Thought: now divide
...
Final Answer: ~26.8x              ───►    parse_step() → ("final", "...")  → return
```

**When to use it:** when the model doesn't support native tool calling (small open-source
models, older models, raw completion APIs), or when you want full control over the protocol.

**Pitfalls (all handled in the code):**

| Problem | What happens | Fix |
|---|---|---|
| Hallucinated observation | The model writes `Observation: 300m` itself | `truncate_hallucinated_observation()`, `stop=["Observation:"]` in the API |
| Broken format | The model forgets the format | send back a `FORMAT ERROR` observation, the model corrects itself |
| A string instead of JSON | `Action Input: eiffel tower` | accept a string if the tool has a single argument |
| Unknown tool | `Action: google` | list the available tools in the error observation |
| Infinite loop | The model never gives a Final Answer | `max_steps` |

### (b) Native function calling

In modern APIs (OpenAI, Anthropic, Gemini, Groq...) the model returns **structured `tool_calls`**.
The provider does the parsing, not us. The loop is the same.

```
 messages + tool schemas ──► LLM ──► {tool_calls: [{name: "lookup", arguments: {...}}]}
                                          │
             tool result (role="tool") ◄──┘
                     │
                     └──► LLM ──► ... ──► plain text = final answer
```

Bonus: **parallel tool calls** in a single turn (both lookups at once), which is hard in the
text style.

### Comparison

| | Text ReAct | Native function calling |
|---|---|---|
| Model requirement | Any text model | A tool-calling model |
| Parsing | Us (regex, fragile) | The provider (robust JSON) |
| Explicit "Thought" | Always visible | Optional (the model may add text if it wants) |
| Parallel calls | Hard | Built-in |
| Tokens | More (format instructions + scratchpad) | Fewer |
| Production default | Fallback | **Use this** |

## 3. Variants / subtypes

- **Zero-shot ReAct:** format instructions only (this project).
- **Few-shot ReAct:** 1-3 solved examples in the prompt: raises accuracy for weak models.
- **ReAct + reflection:** self-critique on failure (see `06-reflection`).
- **ReAct with parallel tools:** multiple calls in one step, in the native style.
- **ReAct vs Plan-and-Execute vs ReWOO:** ReAct makes an LLM call on every step (adaptive, but
  expensive). ReWOO plans all calls upfront (cheap, but less adaptive). See `05` and `09`.

## 4. When to use it, when not

**Use it:** open-ended tasks where the next step depends on the previous result (research,
debugging, customer support lookups).

**Don't use it:** tasks with fixed steps (prompt chaining is cheaper and predictable), or when
latency is very critical (every step = one LLM round trip).

## 5. Production pitfalls

- **Treat tool output as untrusted:** no `eval()` in the calculator, use the AST-based `safe_eval()`.
  Tool results can also carry prompt injection ("ignore previous instructions...").
- **Context growth:** messages grow on every step → tokens and cost grow. Truncate/summarize long tool
  outputs.
- Keep both a **step limit + timeout**.
- **Log the trace:** thought/action/observation is the only way to see where the agent went astray.

## 6. How this project uses it

| Concept | File / function |
|---|---|
| Tools (safe calculator, KB lookup) | `react_tools.py` → `safe_eval`, `calculator`, `lookup` |
| Text ReAct prompt/format | `react_textloop.py` → `REACT_SYSTEM` |
| Output parsing | `react_textloop.py` → `parse_step()` |
| Hallucinated observation fix | `react_textloop.py` → `truncate_hallucinated_observation()` |
| Loop + format-error recovery + max_steps | `react_textloop.py` → `run_react_text()` |
| Native function calling | `react_native.py` → `build_native_agent()` (agentkit `Agent`) |
| Side-by-side comparison | `main.py` (prints llm_calls + tokens for both) |

Notice in the offline demo: the native style made 3 LLM calls (both lookups in parallel), the text
style made 4, and the text style used noticeably more tokens (format instructions + scratchpad).
