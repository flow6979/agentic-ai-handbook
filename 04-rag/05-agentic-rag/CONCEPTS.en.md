**Language:** [Hinglish](CONCEPTS.md) · English

# Agentic RAG: concepts (English)

## The problem with naive RAG

In projects 01-04 the flow was **fixed**: retrieve → answer for every question. The weaknesses of this rigid pipeline:

| Question | What naive RAG does | What should happen |
|---|---|---|
| "hello!" | Retrieves for no reason | Reply directly |
| "What is the refund window and how much sick leave?" | One query, may find only one topic | Two separate searches |
| "How many vacation days?" (doc says "paid leave") | Retrieval fails, it still makes up an answer | Rephrase the query and try again |
| Retrieved chunk is irrelevant | The LLM makes something up from it | Reject the chunk |
| The LLM said "30 days", the doc says 12 | That goes straight to the user | Check it, fix it |

**Agentic RAG** = turn retrieval into a **decision**, where the LLM/agent thinks: *do I need to search? where?
with which query? is what I found useful? does the answer match the source?*

## Two styles

```
 A) TOOL-CALLING AGENT (autonomous)                B) CORRECTIVE PIPELINE (controlled graph)

   user ─► Agent loop                               user ─► ROUTE ──none──► direct reply
            │  LLM: "search_hr('sick leave')"                  │ [hr, product]
            ▼                                                  ▼
         tool result ─► LLM: "enough? or search more?"      DECOMPOSE ─► [q1, q2]
            │  (loop, max_steps)                               │ for each sub-question:
            ▼                                                  ▼
         final answer + citations                          RETRIEVE ─► GRADE ─┬─ relevant ──┐
                                                               ▲              │ none        │
   + flexible, less code                                       └── REWRITE ◄──┘ (1 retry)   │
   - unpredictable, hard to test                                                still none ─┼─► "not found"
   - nothing stops a wrong decision                                                         ▼
                                                            ANSWER ─► CHECK groundedness ─┬─ ok ──► answer
                                                               ▲                          │ fail
                                                               └── regenerate w/ feedback ◄┘ (1 retry, then disclaimer)

                                                           + every step visible + testable
                                                           - more LLM calls, more code
```

Real systems are often **a mix of both**: libraries like LangGraph build a B-style graph
where some nodes are agent-style.

## Each building block

### 1. Retrieval as a tool (style A)
Each knowledge base becomes a tool: `search_hr(query)`, `search_product(query)`.
The **tool description** is the LLM's routing guide ("Contains: leave, travel, working hours..."),
so writing a good description = good routing. See `make_search_tool()`.

### 2. Routing (multiple knowledge bases)
Why keep different data in different KBs instead of all in one?
- **Precision**: HR's "leave" and product's "return" do not get mixed
- **Security**: HR docs are for employees only (the customer bot should never get that KB)
- **Separate tuning**: each KB can have its own chunking/embedder

Router types:
| Type | How | Trade-off |
|---|---|---|
| **LLM router** (here, `Route` schema) | The LLM looks at the KB list and chooses | Flexible, 1 extra call |
| Embedding router | query vs KB description similarity | Fast, cheap, less smart |
| Keyword/rules | "leave" → hr | Predictable, brittle |
| Classifier model | a small trained model | Fast + accurate, needs training data |

A line like `kb_names = [n for n in route.kbs if n in valid]` is very important: the LLM may invent
an unknown KB name ("made_up_kb"), so ignore it.

### 3. Query transformation
```
 Decomposition:  "refund window and sick leave?" ─► ["What is the refund window?", "How many sick leave days?"]
 Rewriting:      "vacation days"                 ─► "paid leave days"   (the doc's vocabulary)
 Condensation:   follow-up + history ─► standalone (project 02)
 HyDE:           have the LLM write a "fake answer", embed THAT and search with it
                 (answer-like text sits closer to the chunks that contain the answer)
 Multi-query:    3-5 paraphrases of one question, union of all their results
 Step-back:      turn a specific question into a general one ("doctor note for 12 days of sick leave?" → "sick leave rules")
```
Decomposition + rewriting are implemented here; HyDE/multi-query are in the tinker exercises.

### 4. Corrective RAG (CRAG): relevance grading
Retrieval top-k **always returns something**, even if it is irrelevant. A grader (LLM judge) checks each
passage: "is this useful for the question?"
- Some relevant → send only those forward (less noise)
- None → **rewrite the query** and search again
- Still none → the CRAG paper uses a **web search fallback** (see `03-web-agents`); here a clear "not found"

Grading is done for all passages in one call (batched): a separate call per passage = expensive.

### 5. Self-RAG style groundedness check
The answer is written, but is it **supported** by the passages? One more LLM call checks it and
lists unsupported claims. If it fails, **regenerate** with feedback about those claims. If it still fails,
attach a **disclaimer** to the answer. Never silently send a wrong answer.

Related ideas:
- **Self-RAG** (paper): the model itself decides via special tokens whether to retrieve, and critiques its own output
- **Adaptive RAG**: look at the question's complexity and choose no-retrieval / single-step / multi-step

## Cost and latency math

```
 Naive RAG:      1 LLM call
 Corrective:     route + decompose + (grade [+ rewrite + grade]) × subqs + answer + check [+ regen + check]
                 = best case ~5, worst case ~12 calls
```
So:
- Use a small/cheap model for routing/grading, and a big model only for the final answer
- Give every step a skip condition (for chitchat, reply directly after routing, only 2 calls)
- A **hard limit** on retry loops (`max_regenerations`, rewrite only once)

## When to use what

| Situation | Choose |
|---|---|
| One KB, simple FAQ, low latency | Naive RAG (01) |
| Many KBs, mixed questions, chitchat too | Router + agent |
| A wrong answer is very costly (HR, legal, medical) | Corrective + groundedness check |
| Open-ended research questions | Tool-calling agent (multiple searches) |

## How this project uses it

| Concept | File / function |
|---|---|
| Multiple knowledge bases | `agenticrag_core.py` → `KnowledgeBase`, `default_kbs()` (data/hr, data/product) |
| Retrieval as a tool | `make_search_tool()` |
| Autonomous tool-calling RAG agent | `build_rag_agent()`, `AGENT_SYSTEM` |
| LLM router + unknown-KB guard | `Route`, `ROUTE_PROMPT`, `CorrectiveRAG.run()` |
| Query decomposition | `SubQuestions`, `DECOMPOSE_PROMPT` |
| Relevance grading (batched) + rewrite retry | `Grades`, `Rewrite`, `_retrieve_graded()` |
| Groundedness check + regenerate + disclaimer | `GroundCheck`, `CHECK_PROMPT`, loop in `run()` |
| Visible trace of every decision | `CRAGResult.trace` |
| Offline rule-based fake LLM (TASK: markers) | `offline_agentic_llm()` |
