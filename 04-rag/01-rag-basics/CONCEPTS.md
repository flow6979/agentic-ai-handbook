# RAG Basics: concepts (Hinglish)

## Problem kya hai?

LLM ne training ke time internet padha tha, lekin **tumhari company ke docs** usne kabhi nahi dekhe
(refund policy, HR rules, product manual). Agar seedha poochoge "NimbusKart mein card refund kitne din
mein aata hai?" to LLM ya to mana karega ya **hallucinate** karega (confident hoke galat bolega).

**RAG = Retrieval-Augmented Generation**
- **Retrieval**: pehle apne docs mein se relevant tukde dhoondo
- **Augmented**: un tukdon ko prompt mein daal do
- **Generation**: ab LLM unhi tukdon ko padh ke jawab likhe

Ek line mein: **LLM ko open-book exam dilwana.**

## Poora pipeline

RAG ke do phases hote hain: **indexing** (ek baar, offline) aur **querying** (har sawaal pe).

```
 ===================== INDEXING (ek baar) =====================

  data/*.md ──► [1. LOAD] ──► Document(id, text)
                                  │
                                  ▼
                            [2. CHUNK]  400 chars ke tukde
                                  │
                                  ▼
                            [3. EMBED]  har chunk -> vector [0.12, -0.4, ...]
                                  │
                                  ▼
                            [4. STORE]  (chunk, vector) list = "vector store"

 ===================== QUERY (har sawaal pe) ==================

  "Card refund kitne din?" ──► [EMBED question] ──► q_vector
                                                        │
                                                        ▼
                           [5. RETRIEVE] q_vector vs sab chunk vectors (cosine)
                                          top-k chunks nikaalo
                                                        │
                                   score < min_score? ──┼── haan ──► "I don't know" (LLM call hi nahi)
                                                        │ nahi
                                                        ▼
                           [6. AUGMENT] prompt = rules + CONTEXT(chunks) + QUESTION
                                                        │
                                                        ▼
                           [7. GENERATE] LLM ──► "Card refunds take 5-7 days [refund_policy.md]"
```

## Har step detail mein

### 1. Load
Files padho aur `Document(id, text, metadata)` banao. `id` (file name) baad mein **citation** ban jata hai.
Real duniya mein loaders PDF, HTML, DOCX, Notion, Confluence sab ke liye hote hain (project 02 mein PDF).

### 2. Chunking: sabse underrated step
Poora doc ek saath embed kyun nahi karte?
- Embedding ek chhota "summary vector" hai. Bade doc mein 10 topics hon to vector sabka average ban jata hai
  aur kisi specific sawaal se match nahi hota.
- LLM ke prompt mein jagah (context window) limited hai aur tokens paise lete hain.

Isliye doc ko chhote **chunks** mein todte hain. Is project mein 3 strategies hain:

```
 FIXED (size=20, overlap=5)          RECURSIVE                          SENTENCE
 "NimbusKart offers a 30-d"          pehle "\n\n" (paragraph) pe todo   poore sentences jodo
       "a 30-day refund wind"        piece bada? "\n" pe todo           jab tak max_chars
             ↑ overlap               ab bhi bada? ". " pe, phir " "     na ho jaaye
 + simple, predictable               + structure bachta hai              + sentence kabhi nahi tootta
 - words beech se toot'te             - thoda complex                     - sentence bahut lamba ho to
                                     (LangChain ka default)                chunk bhi lamba
```

**Overlap kyun?** Agar answer do chunks ki boundary pe ho ("...refund 5 to | 7 business days"), to
overlap ki wajah se kam se kam ek chunk mein poora sentence aa jata hai.

**Chunk size trade-off:**

| Chhote chunks (100-200) | Bade chunks (800-1500) |
|---|---|
| Precise match | Zyada context ek saath |
| Context adhoora reh sakta hai | Noise zyada, similarity dilute |
| Zyada chunks = zyada embedding cost | Kam chunks |

Koi magic number nahi hai. Apne data pe **evaluate karke** chuno (dekho `06-rag-evaluation`).

Aur bhi chunking types (yahan implement nahi kiye):
- **Semantic chunking**: jahan embedding similarity achanak gire wahan todo (topic badla)
- **Document-structure aware**: markdown headings, HTML tags, code functions ke hisaab se
- **Parent-child / small-to-big**: search chhote chunk pe, LLM ko bada parent chunk bhejo
- **Late chunking / contextual chunk headers**: har chunk ke upar doc ka title/summary jod do taaki
  "It costs 99 rupees" jaise chunk ko pata ho "it" kya hai

### 3. Embeddings
Embedding model text ko ek fixed-length vector mein badalta hai. **Similar meaning = paas paas vectors.**

```
 "refund policy"          ──► [ 0.21, -0.03, 0.88, ... ]  ─┐
 "how do I get money back"──► [ 0.19, -0.01, 0.85, ... ]  ─┴─ paas (cosine ~0.9)
 "python async tutorial"  ──► [-0.70,  0.44, 0.02, ... ]  ─── door (cosine ~0.1)
```

**Cosine similarity** = do vectors ke beech ka angle. 1 = same direction, 0 = koi relation nahi.

> Is repo ka `get_embedder("local")` ek **hashing embedder** hai: words ko hash karke vector banata hai.
> Yeh free aur offline hai, lekin **meaning nahi samajhta** ("car" aur "automobile" alag). Iski ek
> kamzori tum khud dekh sakte ho: "Who won the cricket world cup" ko shipping doc se 0.22 score milta hai,
> sirf common words ("the", "who") ki wajah se. Real kaam ke liye `EMBED_MODEL=gemini:text-embedding-004`
> ya `ollama:nomic-embed-text` lo.

### 4. Vector store
Is project mein simplest store hai: Python list + har query pe sab se cosine (brute force, O(N)).
Chhote data (10k chunks) ke liye perfect. Bade data ke liye real vector DB chahiye (project 04 mein).

### 5. Retrieve: top-k
Question ko embed karo, sab chunks se score nikaalo, top `k` lo.
- `k` chhota: answer miss ho sakta hai
- `k` bada: prompt mein noise, LLM confuse ("lost in the middle" problem), cost zyada

**`min_score` gate**: agar best chunk bhi kam score ka hai, to LLM ko call hi mat karo, seedha
"I don't know". Yeh hallucination rokne ka sasta tareeka hai. Lekin threshold embedder pe depend karta hai
(har model ke scores ki range alag hoti hai), isliye ise tune karna padta hai.

### 6. Augment: prompt design
```
SYSTEM: Answer using ONLY the context. Cite [source]. Nahi pata to "I don't know".
USER:   CONTEXT:
        [1] (source: refund_policy.md)
        ...chunk text...
        [2] (source: nimbus_plus.md)
        ...
        QUESTION: How long do card refunds take?
```
Teen important rules:
1. **Grounding**: "ONLY the context" se outside knowledge band hoti hai
2. **Citations**: har fact ka source, taaki user verify kar sake aur hum eval kar sakein
3. **Refusal path**: nahi pata to bolna allowed hai, varna model kuch bhi bana dega

### 7. Generate
LLM jawab likhta hai. Hum answer mein se `[file.md]` citations regex se nikaalte hain (`RAGAnswer.sources`).

## RAG ke failure modes (yaad rakho)

```
 Galat jawab aaya? Pehle yeh check karo ki galti KAHAN hui:

   Retrieval fail?  ── sahi chunk top-k mein aaya hi nahi   ──► chunking / embedder / k / hybrid search
        │
   Generation fail? ── chunk aaya, phir bhi LLM ne galat bola ──► prompt / model / context order
```
Hamesha `--show-chunks` se dekho ki retrieve kya hua. 80% RAG bugs retrieval mein hote hain.

## Kab RAG use karo, kab nahi

| RAG achha hai | RAG theek nahi |
|---|---|
| Bade, badalte docs (policies, manuals, wiki) | Poora data chhota hai (seedha prompt mein daal do) |
| Citations chahiye | "Sab docs ka summary do" (aggregation: har chunk chahiye) |
| Data private hai, fine-tune nahi karna | Exact numbers/joins (SQL tool better) |

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Load | `ragbasics_pipeline.py` → `load_folder()` |
| Fixed / recursive / sentence chunking | `chunk_fixed()`, `chunk_recursive()`, `chunk_sentences()` |
| Chunk metadata + ids (`refund_policy.md#1`) | `chunk_documents()` |
| Embed + in-memory vector store | `InMemoryVectorStore.add()` (batching) |
| Top-k cosine retrieve | `InMemoryVectorStore.search()` |
| min_score gate ("I don't know" bina LLM ke) | `RAG.answer()` |
| Prompt with numbered context + rules | `SYSTEM_PROMPT`, `build_prompt()` |
| Citation extraction | regex in `RAG.answer()` |
| Offline fake LLM (sentence overlap) | `offline_answerer()` |
| CLI, chunker comparison | `main.py` (`--compare-chunkers`, `--show-chunks`) |
