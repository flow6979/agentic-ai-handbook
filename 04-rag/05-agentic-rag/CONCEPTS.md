**Language:** Hinglish · [English](CONCEPTS.en.md)

# Agentic RAG: concepts (Hinglish)

## Naive RAG ki problem

Projects 01-04 mein flow **fixed** tha: har sawaal pe retrieve → answer. Is rigid pipeline ki kamzoriyan:

| Sawaal | Naive RAG kya karta hai | Kya hona chahiye |
|---|---|---|
| "hello!" | Faltu mein retrieve karta hai | Seedha reply |
| "Refund window aur sick leave kitni?" | Ek query, shayad ek hi topic mile | Do alag searches |
| "Kitne vacation days?" (doc mein "paid leave") | Retrieval fail, fir bhi answer banata hai | Query rephrase karke dobara |
| Retrieved chunk irrelevant | LLM usi se kuch bhi bana deta hai | Chunk reject karo |
| LLM ne "30 days" bola, doc mein 12 | Wahi user ko chala jata hai | Check karo, sudharo |

**Agentic RAG** = retrieval ko ek **decision** bana do, jisme LLM/agent sochta hai: *search karna hai? kahan?
kis query se? jo mila woh kaam ka hai? jawab source se match karta hai?*

## Do styles

```
 A) TOOL-CALLING AGENT (autonomous)                B) CORRECTIVE PIPELINE (controlled graph)

   user ─► Agent loop                               user ─► ROUTE ──none──► direct reply
            │  LLM: "search_hr('sick leave')"                  │ [hr, product]
            ▼                                                  ▼
         tool result ─► LLM: "enough? ya aur search?"       DECOMPOSE ─► [q1, q2]
            │  (loop, max_steps)                               │ har sub-question:
            ▼                                                  ▼
         final answer + citations                          RETRIEVE ─► GRADE ─┬─ relevant ──┐
                                                               ▲              │ none        │
   + flexible, kam code                                        └── REWRITE ◄──┘ (1 retry)   │
   - unpredictable, test karna mushkil                                          still none ─┼─► "not found"
   - galat decision pe kuch nahi rokta                                                      ▼
                                                            ANSWER ─► CHECK groundedness ─┬─ ok ──► answer
                                                               ▲                          │ fail
                                                               └── feedback se regenerate ◄┘ (1 retry, phir disclaimer)

                                                           + har step visible + testable
                                                           - zyada LLM calls, zyada code
```

Real systems mein aksar **dono ka mix** hota hai: LangGraph jaisi libraries B-style graph banati hain
jisme kuch nodes agent-style hote hain.

## Har building block

### 1. Retrieval as a tool (style A)
Har knowledge base ek tool ban jata hai: `search_hr(query)`, `search_product(query)`.
**Tool description** hi LLM ka routing guide hai ("Contains: leave, travel, working hours..."),
isliye description achha likhna = routing achhi. `make_search_tool()` dekho.

### 2. Routing (multiple knowledge bases)
Alag data ko alag KB mein kyun rakhein, sab ek mein kyun nahi?
- **Precision**: HR ka "leave" aur product ka "return" mix na ho
- **Security**: HR docs sirf employees ke liye (customer bot ko wo KB milna hi nahi chahiye)
- **Alag tuning**: har KB ka apna chunking/embedder ho sakta hai

Router types:
| Type | Kaise | Trade-off |
|---|---|---|
| **LLM router** (yahan, `Route` schema) | LLM KB list dekh ke choose kare | Flexible, 1 extra call |
| Embedding router | query vs KB description similarity | Fast, sasta, kam smart |
| Keyword/rules | "leave" → hr | Predictable, brittle |
| Classifier model | chhota trained model | Fast + accurate, training data chahiye |

`kb_names = [n for n in route.kbs if n in valid]` jaisi line bahut important hai: LLM unknown KB ka
naam bana sakta hai ("made_up_kb"), usko ignore karo.

### 3. Query transformation
```
 Decomposition:  "refund window aur sick leave?" ─► ["What is the refund window?", "How many sick leave days?"]
 Rewriting:      "vacation days"                 ─► "paid leave days"   (doc ki vocabulary)
 Condensation:   follow-up + history ─► standalone (project 02)
 HyDE:           LLM se ek "fake answer" likhwao, USKO embed karke search karo
                 (answer jaisa text, answer wale chunks ke zyada paas hota hai)
 Multi-query:    ek sawaal ke 3-5 paraphrases, sab ke results union
 Step-back:      specific sawaal se general sawaal banao ("12 din sick leave pe doctor note?" → "sick leave rules")
```
Yahan decomposition + rewriting implement kiye hain; HyDE/multi-query tinker exercise mein.

### 4. Corrective RAG (CRAG): relevance grading
Retrieval top-k **hamesha kuch na kuch** deta hai, chahe irrelevant ho. Grader (LLM judge) har
passage ko check karta hai: "yeh sawaal ke kaam ka hai?"
- Kuch relevant → sirf unhe aage bhejo (noise kam)
- Kuch nahi → **query rewrite** karke dobara search
- Phir bhi nahi → CRAG paper mein **web search fallback** (dekho `03-web-agents`); yahan saaf "not found"

Grading ek call mein saare passages ka (batched) karte hain: har passage pe alag call = mehenga.

### 5. Self-RAG style groundedness check
Answer ban gaya, lekin kya woh passages se **supported** hai? Ek aur LLM call check karta hai aur
unsupported claims list karta hai. Fail hua to un claims ke feedback ke saath **regenerate**. Phir bhi fail
ho to answer ke saath **disclaimer** lagao. Galat answer ko chupchaap mat bhejo.

Isse related ideas:
- **Self-RAG** (paper): model khud special tokens se decide karta hai retrieve karna hai ya nahi, aur apne output ko critique karta hai
- **Adaptive RAG**: sawaal ki complexity dekh ke no-retrieval / single-step / multi-step choose karo

## Cost aur latency ka hisaab

```
 Naive RAG:      1 LLM call
 Corrective:     route + decompose + (grade [+ rewrite + grade]) × subqs + answer + check [+ regen + check]
                 = best case ~5, worst case ~12 calls
```
Isliye:
- Chhote/saste model se routing/grading karo, bade model se sirf final answer
- Har step ko skip karne ki condition rakho (chitchat pe route ke baad seedha reply, sirf 2 calls)
- Retry loops ki **hard limit** (`max_regenerations`, rewrite sirf 1 baar)

## Kab kya

| Situation | Choose |
|---|---|
| Ek KB, simple FAQ, low latency | Naive RAG (01) |
| Kai KBs, mixed questions, chitchat bhi | Router + agent |
| Galat jawab bahut mehenga (HR, legal, medical) | Corrective + groundedness check |
| Open-ended research questions | Tool-calling agent (multiple searches) |

## Is project mein kaise use ho raha hai

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
