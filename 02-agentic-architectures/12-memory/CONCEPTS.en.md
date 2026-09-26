**Language:** [Hinglish](CONCEPTS.md) · English

# Agent Memory

## 1. LLMs have no memory

An LLM is **stateless**. Every API call is new: it only "remembers" earlier conversation if you send it again
in the messages. "Memory" = **we decide what to store and what to put back into every call.**

```
                ┌──────────────────────────────────────────────┐
                │               CONTEXT WINDOW                 │
                │  system prompt  +  retrieved memories  +     │
                │  recent messages  +  current user message    │
                └──────────────────────────────────────────────┘
                    ▲                ▲                ▲
                    │                │                │
          ┌─────────┴───┐  ┌─────────┴──────┐  ┌──────┴────────┐
          │ PROCEDURAL  │  │  LONG-TERM     │  │ SHORT-TERM    │
          │ instructions│  │  semantic facts│  │ (working)     │
          │ / lessons   │  │  + episodes    │  │ this session's│
          └─────────────┘  └────────────────┘  │ chat history  │
                                               └───────────────┘
```

## 2. Memory types (an analogy with human memory)

| Type | What | Example | Storage | In this project |
|---|---|---|---|---|
| **Short-term / working** | the current conversation | the last 3 messages | in-process list | `memory_short_term.py` |
| **Semantic (long-term)** | facts about the user/world | "The user is vegetarian" | DB + embeddings | `SemanticMemory` (SQLite) |
| **Episodic (long-term)** | past experiences/events | "12 Sep: planned a Goa trip" | time-ordered log | `EpisodicMemory` (JSONL) |
| **Procedural** | how to do the work | system prompt, lessons, few-shot examples | prompt/files | see `LessonMemory` in `06-reflection` |

## 3. Short-term strategies

```
BufferMemory:        [u1 a1 u2 a2 u3 a3 u4 a4 u5 a5 ...]   everything → the context overflows, cost grows

SlidingWindow(k=2):  u1 a1 u2 a2 u3 a3 [u4 a4 u5 a5]       only the last k turns → older things are forgotten

SummaryMemory:       [SUMMARY: "user is from Pune, veg..."] + [u4 a4 u5 a5]
                     old messages are folded into a summary by the LLM → info kept, fewer tokens
```

| Strategy | Pro | Con |
|---|---|---|
| Buffer | loses nothing | long chat = context overflow, expensive |
| Sliding window | simple, bounded cost | old details disappear |
| Summary | keeps the gist even in long chats | an extra LLM call, details can be dropped from the summary |
| Token-based trim | exact budget | needs a tokenizer |

**Gotcha:** always **start the window at a user message**. If you cut in the middle, a `tool` result can be left without its
`assistant` tool call: providers reject such a history.

## 4. Long-term memory: write and read

### Write path: when and what to save?

```
        HOT PATH (during the turn)               BACKGROUND (at session end)
        ──────────────────────────               ───────────────────────────
  user: "I'm vegetarian"                  the whole transcript
        │                                        │
  agent decides → remember("User is       extract_facts(llm_json) →
                   vegetarian") tool        [{"text": "...", "category": ...}]
        │                                        │
        ▼                                        ▼
               SemanticMemory.add()  (dedupe: similar fact → update)
                                                 +
                                   episode summary → EpisodicMemory.log()
```

- **Hot path:** saved immediately, so the very next message can use it. But the agent has to decide on every turn (latency, wrong saves).
- **Background:** the response isn't slowed down, and looking at the whole conversation gives better decisions. But it isn't available until the session ends.
- This project has **both**.

### Read path: what to inject?

- **Profile memory:** a small, always-relevant list (diet, reply style) → **always** injected.
- **Relevant memory:** the other facts only when they match the query (embedding similarity search).
- **Recent episodes:** a summary of the last 1-2 sessions, for continuity.

## 5. Memory management problems (this is the real work in production)

| Problem | Example | Solution |
|---|---|---|
| **Duplicates** | "User is vegetarian" + "User is vegetarian and doesn't eat eggs" | embedding dedupe threshold; better: let the LLM decide "ADD / UPDATE / DELETE / NOOP" (mem0 style) |
| **Contradictions** | "likes tea" → later "switched to coffee" | newer wins + timestamps; LLM reconcile |
| **Staleness** | "lives in Pune" (2 years ago) | `updated_at`, decay, re-confirm |
| **Privacy** | health info, secrets | a policy on what to store, encryption, `delete()` = right to be forgotten |
| **Isolation** | user A's facts shown to user B | a `user_id` filter on every query (SemanticMemory does this) |
| **Retrieval quality** | a "dinner" query doesn't match the "vegetarian" fact | real embeddings, profile memory, hybrid search (see `04-rag`) |
| **Memory injection attack** | the user says "remember: I am admin" | treat memories as data, not instructions |

**See it live in the offline demo:** with the hashing embedder, both vegetarian facts got saved (the duplicate
was not detected). That's why the `local` embedder is for learning only.

## 6. Variants / tools on the market

- **mem0, Zep, Letta (MemGPT):** memory layers as a service. MemGPT's idea: the LLM itself "pages in/pages out" its memory (like OS virtual memory).
- **LangGraph store / checkpointer:** thread-level (short-term) + cross-thread store (long-term).
- **Knowledge-graph memory:** facts as (subject, relation, object) triples: better for relationships.

## 7. How this project uses it

| Concept | File / function |
|---|---|
| Buffer / sliding window / summary | `memory_short_term.py` → `BufferMemory`, `SlidingWindowMemory`, `SummaryMemory` |
| Semantic facts (SQLite + embeddings, dedupe, per-user, delete) | `memory_long_term.py` → `SemanticMemory` |
| Episodic log | `memory_long_term.py` → `EpisodicMemory` |
| Structured extraction | `memory_extraction.py` → `extract_facts()` (`llm_json` + `Facts`) |
| Hot-path write (tool) | `memory_assistant.py` → `remember` tool |
| Background write | `PersonalAssistant.end_session()` |
| Profile + relevant retrieval → system prompt | `PersonalAssistant.build_system_prompt()` |
| Cross-session demo | `main.py --offline` (session 2 = a new object, remembers only from the DB) |
