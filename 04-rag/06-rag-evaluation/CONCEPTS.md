**Language:** Hinglish · [English](CONCEPTS.en.md)

# RAG Evaluation: concepts (Hinglish)

## Eval kyun?

RAG mein 20 knobs hain: chunk size, overlap, chunker type, embedder, k, hybrid ya nahi, reranker,
prompt, model... Har change ke baad 2-3 sawaal manually poochh ke "haan achha lag raha hai" bolna
**vibes-based engineering** hai. Ek change ek sawaal sudhaarta hai aur teen tod deta hai, aur pata bhi nahi chalta.

**Eval = ek fixed test set + metrics.** Har change ke baad chalao, numbers compare karo.
Yeh RAG ka unit test hai.

## Do alag cheezein measure karo

```
                question
                   │
         ┌─────────▼──────────┐
         │     RETRIEVAL      │   ◄── Metric: sahi doc/chunk top-k mein aaya?
         │  (search index)    │       hit@k, MRR, recall@k, precision@k, nDCG
         └─────────┬──────────┘       Sasta: LLM ki zaroorat nahi, sirf labels
                   │ context
         ┌─────────▼──────────┐
         │     GENERATION     │   ◄── Metric: jawab achha hai?
         │       (LLM)        │       faithfulness, answer relevance, correctness
         └─────────┬──────────┘       Mehenga: LLM-as-judge ya humans
                   ▼
                 answer
```
Alag-alag kyun? Galat jawab aaya to pata hona chahiye ki **galti kahan hui**.
Retrieval ne sahi chunk diya hi nahi, to prompt tweak karne se kuch nahi hoga.

## 1. Test set (golden dataset)

`data/eval_set.json`:
```json
{"question": "How long do card refunds take?",
 "relevant_sources": ["refund_policy.md"],      ◄── retrieval ke liye label
 "reference_answer": "5 to 7 business days."}   ◄── correctness ke liye label
```
Kahan se laayein?
- **Real user questions** (logs se), sabse valuable
- Domain expert se likhwao
- **Synthetic**: LLM se har chunk pe "is chunk se kaunse sawaal ban sakte hain" likhwao (fast, lekin easy sawaal banta hai)
- Hard cases zaroor daalo: multi-doc ("Is express free for Plus?" → 2 docs), unanswerable, vocabulary mismatch

50-200 sawaal se shuru karo. Har production bug ek naya test case ban jaye.

## 2. Retrieval metrics

Example: relevant = `shipping.md`, retrieved top-3 = `[refund.md, shipping.md, plus.md]`

| Metric | Formula | Example | Kya batata hai |
|---|---|---|---|
| **Hit@k** (hit rate) | koi relevant top-k mein? 1/0 | 1 | "Mila ya nahi" |
| **MRR** (Mean Reciprocal Rank) | 1 / pehle relevant ka rank | 1/2 = 0.5 | Kitna **upar** mila |
| **Recall@k** | mile relevant / total relevant | 1/1 = 1.0 | Multi-doc sawaalon mein sab mile? |
| Precision@k | relevant in top-k / k | 1/3 | Kitna noise |
| nDCG | graded relevance + position discount | - | Jab relevance 0/1 nahi, 0-3 ho |

```
 Rank:        1          2           3
            refund    shipping ✓    plus
 RR = 1/2 = 0.5        ▲ pehla relevant yahan
```

Is project ke results (local embedder, 12 questions):
```
config               chunks  hit@k    MRR recall
fixed-100/k3             31   1.00   0.92   1.00
fixed-300/ov50/k3        14   1.00   1.00   1.00
para-400/k1              10   0.92   0.92   0.88     ◄── k=1 bahut kam: ek miss + multi-doc recall gira
para-400/k3              10   1.00   0.96   1.00
```
Dhyan do: sirf 5 docs hain, isliye doc-level hit rate aasani se 1.0 ho jata hai. Real eval mein
**chunk-level labels** (kaunsa exact chunk chahiye) aur bade corpus se fark zyada saaf dikhta hai.

## 3. Generation metrics: LLM-as-judge

Answer "achha" hai, yeh regex se nahi naap sakte. Ek LLM ko **judge** banao, rubric do, 1-5 score lo:

| Metric | Sawaal | Kya pakadta hai |
|---|---|---|
| **Faithfulness** (groundedness) | Answer context se supported hai? | Hallucination |
| **Answer relevance** | Answer sawaal ka jawab deta hai? | Off-topic / adhoora jawab |
| **Correctness** | Reference answer se meaning match? | Galat facts (reference chahiye) |
| Context relevance | Retrieved context sawaal ke kaam ka tha? | Retrieval noise |

Offline run mein ek achha example aata hai:
```
F=5 R=2 C=1  How much does express shipping cost?
      -> ## Express shipping              ◄── faithful (context mein hai!) lekin useless
```
Isiliye **ek metric kaafi nahi**: faithfulness 5 hai, lekin relevance aur correctness ne pakad liya.

### Judge ko reliable banana
- **Rubric specific** rakho ("5 = every claim supported") aur structured output (`Judgement` schema, `score` 1-5 validated)
- Score ke saath **reason** maango: debugging mein kaam aata hai, aur score better hota hai
- Judge ke **known biases**: lambe answers ko zyada score, apne model family ke answers ko favour, position bias (pairwise mein)
- Judge ko bhi evaluate karo: 30-50 samples pe human labels se agreement check karo
- Judge ke liye alag (aksar zyada strong) model rakho, generator se different
- Temperature 0, same prompt har baar = reproducible

## 4. Eval workflow

```
  change (chunk size / prompt / model)
          │
          ▼
  retrieval eval (sasta, har change pe) ──► hit/MRR gira? ──► revert
          │ theek
          ▼
  generation eval (mehenga, important changes pe) ──► faithfulness/correctness compare
          │
          ▼
  failures list padho (sabse important step!) ──► naye test cases jodo
```
CI mein retrieval eval har PR pe chala sakte ho (fast, deterministic). Generation eval nightly.

Tools jo yeh kaam bade scale pe karte hain: **Ragas**, **DeepEval**, **TruLens**, **Phoenix (Arize)**,
**LangSmith**, **promptfoo**. Concepts wahi hain jo yahan hain.

## Pitfalls
- Sirf average dekhna: failures list padho, patterns wahan milte hain
- Test set pe overfit: prompt ko test questions ke hisaab se tune karte rehna. Hold-out set rakho
- Eval set purana ho gaya (docs badal gaye, labels nahi)
- Judge pe blind trust: occasionally manually check karo

## Is project mein kaise use ho raha hai

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
