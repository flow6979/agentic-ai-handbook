**Language:** [Hinglish](CONCEPTS.md) · English

# RAG Evaluation: concepts (English)

## Why evaluate?

RAG has 20 knobs: chunk size, overlap, chunker type, embedder, k, hybrid or not, reranker,
prompt, model... Asking 2-3 questions by hand after every change and saying "yes, looks good"
is **vibes-based engineering**. One change fixes one question and breaks three, and you never even notice.

**Eval = a fixed test set + metrics.** Run it after every change and compare the numbers.
This is the unit test of RAG.

## Measure two different things

```
                question
                   │
         ┌─────────▼──────────┐
         │     RETRIEVAL      │   ◄── Metric: did the right doc/chunk make it into top-k?
         │  (search index)    │       hit@k, MRR, recall@k, precision@k, nDCG
         └─────────┬──────────┘       Cheap: no LLM needed, only labels
                   │ context
         ┌─────────▼──────────┐
         │     GENERATION     │   ◄── Metric: is the answer good?
         │       (LLM)        │       faithfulness, answer relevance, correctness
         └─────────┬──────────┘       Expensive: LLM-as-judge or humans
                   ▼
                 answer
```
Why separately? When the answer is wrong, you need to know **where it went wrong**.
If retrieval never returned the right chunk, tweaking the prompt will do nothing.

## 1. Test set (golden dataset)

`data/eval_set.json`:
```json
{"question": "How long do card refunds take?",
 "relevant_sources": ["refund_policy.md"],      ◄── label for retrieval
 "reference_answer": "5 to 7 business days."}   ◄── label for correctness
```
Where do you get it?
- **Real user questions** (from logs), the most valuable
- Have a domain expert write them
- **Synthetic**: have the LLM write "which questions can this chunk answer" for each chunk (fast, but produces easy questions)
- Always include hard cases: multi-doc ("Is express free for Plus?" → 2 docs), unanswerable, vocabulary mismatch

Start with 50-200 questions. Every production bug should become a new test case.

## 2. Retrieval metrics

Example: relevant = `shipping.md`, retrieved top-3 = `[refund.md, shipping.md, plus.md]`

| Metric | Formula | Example | What it tells you |
|---|---|---|---|
| **Hit@k** (hit rate) | any relevant in top-k? 1/0 | 1 | "Found or not" |
| **MRR** (Mean Reciprocal Rank) | 1 / rank of the first relevant | 1/2 = 0.5 | How **high up** it was found |
| **Recall@k** | relevant found / total relevant | 1/1 = 1.0 | For multi-doc questions, were all found? |
| Precision@k | relevant in top-k / k | 1/3 | How much noise |
| nDCG | graded relevance + position discount | - | When relevance is 0-3 rather than 0/1 |

```
 Rank:        1          2           3
            refund    shipping ✓    plus
 RR = 1/2 = 0.5        ▲ first relevant is here
```

This project's results (local embedder, 12 questions):
```
config               chunks  hit@k    MRR recall
fixed-100/k3             31   1.00   0.92   1.00
fixed-300/ov50/k3        14   1.00   1.00   1.00
para-400/k1              10   0.92   0.92   0.88     ◄── k=1 is too low: one miss + multi-doc recall dropped
para-400/k3              10   1.00   0.96   1.00
```
Note: there are only 5 docs, so the doc-level hit rate easily reaches 1.0. In a real eval,
**chunk-level labels** (which exact chunk is needed) and a bigger corpus show the differences much more clearly.

## 3. Generation metrics: LLM-as-judge

You cannot measure whether an answer is "good" with a regex. Make an LLM the **judge**, give it a rubric, get a 1-5 score:

| Metric | Question | What it catches |
|---|---|---|
| **Faithfulness** (groundedness) | Is the answer supported by the context? | Hallucination |
| **Answer relevance** | Does the answer actually answer the question? | Off-topic / incomplete answer |
| **Correctness** | Does its meaning match the reference answer? | Wrong facts (needs a reference) |
| Context relevance | Was the retrieved context useful for the question? | Retrieval noise |

The offline run produces a good example:
```
F=5 R=2 C=1  How much does express shipping cost?
      -> ## Express shipping              ◄── faithful (it is in the context!) but useless
```
That is why **one metric is not enough**: faithfulness is 5, but relevance and correctness caught it.

### Making the judge reliable
- Keep the **rubric specific** ("5 = every claim supported") and use structured output (`Judgement` schema, `score` 1-5 validated)
- Ask for a **reason** along with the score: it helps with debugging, and the score gets better
- The judge's **known biases**: higher scores for long answers, favouring answers from its own model family, position bias (in pairwise)
- Evaluate the judge too: check agreement with human labels on 30-50 samples
- Use a separate (often stronger) model for the judge, different from the generator
- Temperature 0, the same prompt every time = reproducible

## 4. Eval workflow

```
  change (chunk size / prompt / model)
          │
          ▼
  retrieval eval (cheap, on every change) ──► hit/MRR dropped? ──► revert
          │ fine
          ▼
  generation eval (expensive, on important changes) ──► compare faithfulness/correctness
          │
          ▼
  read the failures list (the most important step!) ──► add new test cases
```
You can run the retrieval eval in CI on every PR (fast, deterministic). Run the generation eval nightly.

Tools that do this at a larger scale: **Ragas**, **DeepEval**, **TruLens**, **Phoenix (Arize)**,
**LangSmith**, **promptfoo**. The concepts are the same as here.

## Pitfalls
- Looking only at the average: read the failures list, that is where the patterns are
- Overfitting to the test set: tuning the prompt again and again for the test questions. Keep a hold-out set
- The eval set went stale (the docs changed, the labels did not)
- Blind trust in the judge: check it by hand now and then

## How this project uses it

| Concept | File / function |
|---|---|
| Golden dataset (sources + reference answers) | `data/eval_set.json`, `load_eval_set()` |
| System under test (configurable chunking + k) | `RetrievalConfig`, `Index` |
| hit@k, MRR, recall@k | `hit_at_k()`, `reciprocal_rank()`, `recall_at_k()` |
| Aggregation + failure list | `evaluate_retrieval()` → `RetrievalReport.failures` |
| Config comparison table | `compare_configs()`, `CONFIGS` in `main.py` |
| LLM-as-judge (faithfulness, relevance, correctness) | `FAITHFULNESS_PROMPT`, `RELEVANCE_PROMPT`, `CORRECTNESS_PROMPT`, `judge()` |
| Validated score schema (1-5) | `Judgement` (pydantic `Field(ge=1, le=5)`) |
| End-to-end generation eval | `evaluate_generation()` |
| Offline fake answerer + judge | `offline_answerer()`, `offline_judge()` |
