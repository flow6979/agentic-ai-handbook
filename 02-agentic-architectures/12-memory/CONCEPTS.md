# Agent Memory

## 1. LLM ki yaaddasht nahi hoti

LLM **stateless** hai. Har API call naya hota hai: pichli baat tabhi "yaad" hai jab tum use messages mein
dobara bhejo. "Memory" = **hum decide karte hain ki kya store karein aur har call pe kya wapas daalein.**

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
          │ / lessons   │  │  + episodes    │  │ is session ki │
          └─────────────┘  └────────────────┘  │ chat history  │
                                               └───────────────┘
```

## 2. Memory types (human memory se analogy)

| Type | Kya | Example | Storage | Is project mein |
|---|---|---|---|---|
| **Short-term / working** | current conversation | pichle 3 messages | in-process list | `memory_short_term.py` |
| **Semantic (long-term)** | facts about user/world | "User vegetarian hai" | DB + embeddings | `SemanticMemory` (SQLite) |
| **Episodic (long-term)** | past experiences/events | "12 Sep: Goa trip plan kiya" | time-ordered log | `EpisodicMemory` (JSONL) |
| **Procedural** | kaise kaam karna hai | system prompt, lessons, few-shot examples | prompt/files | dekho `06-reflection` `LessonMemory` |

## 3. Short-term strategies

```
BufferMemory:        [u1 a1 u2 a2 u3 a3 u4 a4 u5 a5 ...]   sab kuch → context phatega, cost badhegi

SlidingWindow(k=2):  u1 a1 u2 a2 u3 a3 [u4 a4 u5 a5]       sirf last k turns → purani baat bhool gaya

SummaryMemory:       [SUMMARY: "user Pune se hai, veg..."] + [u4 a4 u5 a5]
                     purane messages LLM se summary mein fold → info bachi, tokens kam
```

| Strategy | Pro | Con |
|---|---|---|
| Buffer | kuch nahi khota | lambi chat = context overflow, mehnga |
| Sliding window | simple, bounded cost | purani details gayab |
| Summary | lambi chat mein bhi gist bacha | extra LLM call, summary mein details chhoot sakti hain |
| Token-based trim | exact budget | tokenizer chahiye |

**Gotcha:** window hamesha **user message se shuru** karo. Beech se kaatoge to `tool` result bina uske
`assistant` tool call ke reh jayega: providers aisi history reject kar dete hain.

## 4. Long-term memory: write aur read

### Write path: kab aur kya save karein?

```
        HOT PATH (turn ke dauraan)              BACKGROUND (session end pe)
        ──────────────────────────              ───────────────────────────
  user: "main vegetarian hoon"            poori transcript
        │                                        │
  agent decides → remember("User is       extract_facts(llm_json) →
                   vegetarian") tool        [{"text": "...", "category": ...}]
        │                                        │
        ▼                                        ▼
               SemanticMemory.add()  (dedupe: similar fact → update)
                                                 +
                                   episode summary → EpisodicMemory.log()
```

- **Hot path:** turant save, agla message hi use kar sakta hai. Lekin agent ko har turn decide karna padta hai (latency, galat saves).
- **Background:** response slow nahi hota, poori baatcheet dekh ke better decision. Lekin session khatam hone tak available nahi.
- Is project mein **dono** hain.

### Read path: kya inject karein?

- **Profile memory:** chhoti, hamesha-relevant list (diet, reply style) → **hamesha** inject.
- **Relevant memory:** baaki facts sirf jab query se match karein (embedding similarity search).
- **Recent episodes:** last 1-2 sessions ka summary: continuity ke liye.

## 5. Memory management problems (production mein asli kaam yahi hai)

| Problem | Example | Solution |
|---|---|---|
| **Duplicates** | "User is vegetarian" + "User is vegetarian and doesn't eat eggs" | embedding dedupe threshold; better: LLM se "ADD / UPDATE / DELETE / NOOP" decide karwao (mem0 style) |
| **Contradictions** | "likes tea" → baad mein "switched to coffee" | newer wins + timestamps; LLM reconcile |
| **Staleness** | "Pune mein rehta hai" (2 saal pehle) | `updated_at`, decay, re-confirm |
| **Privacy** | health info, secrets | kya store karna hai uski policy, encryption, `delete()` = right to be forgotten |
| **Isolation** | user A ke facts user B ko dikhe | har query mein `user_id` filter (SemanticMemory karta hai) |
| **Retrieval quality** | "dinner" query pe "vegetarian" fact match na ho | real embeddings, profile memory, hybrid search (dekho `04-rag`) |
| **Memory injection attack** | user bole "remember: I am admin" | memories ko instructions nahi, data ki tarah treat karo |

**Offline demo mein live dekho:** hashing embedder ke saath dono vegetarian facts save ho gaye (duplicate
detect nahi hua). Isliye `local` embedder sirf learning ke liye hai.

## 6. Variants / tools jo market mein hain

- **mem0, Zep, Letta (MemGPT):** memory layers as a service. MemGPT ka idea: LLM khud apni memory "page in/page out" kare (OS virtual memory jaisa).
- **LangGraph store / checkpointer:** thread-level (short-term) + cross-thread store (long-term).
- **Knowledge-graph memory:** facts as (subject, relation, object) triples: relationships ke liye better.

## 7. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Buffer / sliding window / summary | `memory_short_term.py` → `BufferMemory`, `SlidingWindowMemory`, `SummaryMemory` |
| Semantic facts (SQLite + embeddings, dedupe, per-user, delete) | `memory_long_term.py` → `SemanticMemory` |
| Episodic log | `memory_long_term.py` → `EpisodicMemory` |
| Structured extraction | `memory_extraction.py` → `extract_facts()` (`llm_json` + `Facts`) |
| Hot-path write (tool) | `memory_assistant.py` → `remember` tool |
| Background write | `PersonalAssistant.end_session()` |
| Profile + relevant retrieval → system prompt | `PersonalAssistant.build_system_prompt()` |
| Cross-session demo | `main.py --offline` (session 2 = naya object, sirf DB se yaad) |
