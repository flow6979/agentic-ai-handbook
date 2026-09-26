**Language:** [Hinglish](CONCEPTS.md) · English

# RAG Basics: concepts (English)

## What is the problem?

The LLM read the internet during training, but it has never seen **your company's docs**
(refund policy, HR rules, product manual). If you ask directly "How many days does a card refund take at NimbusKart?",
the LLM will either refuse or **hallucinate** (say something wrong with confidence).

**RAG = Retrieval-Augmented Generation**
- **Retrieval**: first find the relevant pieces in your own docs
- **Augmented**: put those pieces into the prompt
- **Generation**: now the LLM reads those pieces and writes the answer

In one line: **give the LLM an open-book exam.**

## The whole pipeline

RAG has two phases: **indexing** (once, offline) and **querying** (on every question).

```
 ===================== INDEXING (once) ========================

  data/*.md ──► [1. LOAD] ──► Document(id, text)
                                  │
                                  ▼
                            [2. CHUNK]  pieces of 400 chars
                                  │
                                  ▼
                            [3. EMBED]  each chunk -> vector [0.12, -0.4, ...]
                                  │
                                  ▼
                            [4. STORE]  (chunk, vector) list = "vector store"

 ===================== QUERY (every question) =================

  "How many days for a card refund?" ──► [EMBED question] ──► q_vector
                                                        │
                                                        ▼
                           [5. RETRIEVE] q_vector vs all chunk vectors (cosine)
                                          take the top-k chunks
                                                        │
                                   score < min_score? ──┼── yes ──► "I don't know" (no LLM call at all)
                                                        │ no
                                                        ▼
                           [6. AUGMENT] prompt = rules + CONTEXT(chunks) + QUESTION
                                                        │
                                                        ▼
                           [7. GENERATE] LLM ──► "Card refunds take 5-7 days [refund_policy.md]"
```

## Each step in detail

### 1. Load
Read the files and build `Document(id, text, metadata)`. The `id` (file name) later becomes the **citation**.
In the real world there are loaders for PDF, HTML, DOCX, Notion, Confluence and more (PDF in project 02).

### 2. Chunking: the most underrated step
Why not embed the whole doc at once?
- An embedding is a small "summary vector". If a big doc has 10 topics, the vector becomes the average of all of them
  and does not match any specific question.
- Space in the LLM prompt (the context window) is limited and tokens cost money.

So we break the doc into small **chunks**. This project has 3 strategies:

```
 FIXED (size=20, overlap=5)          RECURSIVE                          SENTENCE
 "NimbusKart offers a 30-d"          first split on "\n\n" (paragraph)  join whole sentences
       "a 30-day refund wind"        piece too big? split on "\n"       until max_chars
             ↑ overlap               still too big? on ". ", then " "   is reached
 + simple, predictable               + keeps structure                  + never breaks a sentence
 - words break in the middle         - a bit more complex               - a very long sentence makes
                                     (LangChain's default)                a long chunk
```

**Why overlap?** If the answer sits on the boundary of two chunks ("...refund 5 to | 7 business days"),
overlap makes sure at least one chunk contains the full sentence.

**Chunk size trade-off:**

| Small chunks (100-200) | Large chunks (800-1500) |
|---|---|
| Precise match | More context at once |
| Context may be incomplete | More noise, diluted similarity |
| More chunks = more embedding cost | Fewer chunks |

There is no magic number. Choose by **evaluating** on your own data (see `06-rag-evaluation`).

More chunking types (not implemented here):
- **Semantic chunking**: split where embedding similarity suddenly drops (the topic changed)
- **Document-structure aware**: split by markdown headings, HTML tags, code functions
- **Parent-child / small-to-big**: search on the small chunk, send the larger parent chunk to the LLM
- **Late chunking / contextual chunk headers**: prepend the doc title/summary to each chunk so that
  a chunk like "It costs 99 rupees" knows what "it" is

### 3. Embeddings
An embedding model turns text into a fixed-length vector. **Similar meaning = vectors close together.**

```
 "refund policy"          ──► [ 0.21, -0.03, 0.88, ... ]  ─┐
 "how do I get money back"──► [ 0.19, -0.01, 0.85, ... ]  ─┴─ close (cosine ~0.9)
 "python async tutorial"  ──► [-0.70,  0.44, 0.02, ... ]  ─── far (cosine ~0.1)
```

**Cosine similarity** = the angle between two vectors. 1 = same direction, 0 = no relation.

> This repo's `get_embedder("local")` is a **hashing embedder**: it hashes words to build a vector.
> It is free and offline, but it **does not understand meaning** ("car" and "automobile" are different). You can see
> one of its weaknesses yourself: "Who won the cricket world cup" gets a 0.22 score against the shipping doc,
> only because of common words ("the", "who"). For real work use `EMBED_MODEL=gemini:text-embedding-004`
> or `ollama:nomic-embed-text`.

### 4. Vector store
This project uses the simplest store: a Python list + cosine against everything on every query (brute force, O(N)).
Perfect for small data (10k chunks). Large data needs a real vector DB (in project 04).

### 5. Retrieve: top-k
Embed the question, score it against all chunks, take the top `k`.
- `k` too small: the answer may be missed
- `k` too large: noise in the prompt, the LLM gets confused (the "lost in the middle" problem), higher cost

**`min_score` gate**: if even the best chunk has a low score, do not call the LLM at all, just say
"I don't know". This is a cheap way to stop hallucination. But the threshold depends on the embedder
(each model has a different score range), so it needs tuning.

### 6. Augment: prompt design
```
SYSTEM: Answer using ONLY the context. Cite [source]. If you don't know, say "I don't know".
USER:   CONTEXT:
        [1] (source: refund_policy.md)
        ...chunk text...
        [2] (source: nimbus_plus.md)
        ...
        QUESTION: How long do card refunds take?
```
Three important rules:
1. **Grounding**: "ONLY the context" shuts off outside knowledge
2. **Citations**: a source for every fact, so the user can verify and we can evaluate
3. **Refusal path**: saying "I don't know" is allowed, otherwise the model will make something up

### 7. Generate
The LLM writes the answer. We extract the `[file.md]` citations from the answer with a regex (`RAGAnswer.sources`).

## RAG failure modes (remember these)

```
 Got a wrong answer? First check WHERE it went wrong:

   Retrieval fail?  ── the right chunk never made it into top-k ──► chunking / embedder / k / hybrid search
        │
   Generation fail? ── the chunk came, but the LLM still said it wrong ──► prompt / model / context order
```
Always use `--show-chunks` to see what was retrieved. 80% of RAG bugs are in retrieval.

## When to use RAG, when not to

| RAG is good | RAG is not a good fit |
|---|---|
| Large, changing docs (policies, manuals, wiki) | All the data is small (just put it in the prompt) |
| Citations needed | "Summarize all docs" (aggregation: needs every chunk) |
| The data is private and you do not want to fine-tune | Exact numbers/joins (a SQL tool is better) |

## How this project uses it

| Concept | File / function |
|---|---|
| Load | `ragbasics_pipeline.py` → `load_folder()` |
| Fixed / recursive / sentence chunking | `chunk_fixed()`, `chunk_recursive()`, `chunk_sentences()` |
| Chunk metadata + ids (`refund_policy.md#1`) | `chunk_documents()` |
| Embed + in-memory vector store | `InMemoryVectorStore.add()` (batching) |
| Top-k cosine retrieve | `InMemoryVectorStore.search()` |
| min_score gate ("I don't know" without the LLM) | `RAG.answer()` |
| Prompt with numbered context + rules | `SYSTEM_PROMPT`, `build_prompt()` |
| Citation extraction | regex in `RAG.answer()` |
| Offline fake LLM (sentence overlap) | `offline_answerer()` |
| CLI, chunker comparison | `main.py` (`--compare-chunkers`, `--show-chunks`) |
