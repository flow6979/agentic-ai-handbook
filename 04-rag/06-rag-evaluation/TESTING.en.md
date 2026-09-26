**Language:** [Hinglish](TESTING.md) · English

# RAG Evaluation: how to run, test and tinker

Setup: from the repo root, `source .venv/bin/activate && pip install -e ".[all]"`.

## 1. Retrieval eval (no LLM, no key)
```bash
python 04-rag/06-rag-evaluation/main.py retrieval
```
Expected:
```
config               chunks  hit@k    MRR recall
fixed-100/k3             31   1.00   0.92   1.00
fixed-300/ov50/k3        14   1.00   1.00   1.00
para-400/k1              10   0.92   0.92   0.88
                      miss: Does NimbusKart ship internationally?
...
```
With a real embedder: `EMBED_MODEL=gemini:text-embedding-004 python ... retrieval`, then compare the numbers.

## 2. Generation eval
```bash
python 04-rag/06-rag-evaluation/main.py generation --offline --limit 4     # fake answerer + fake judge
python 04-rag/06-rag-evaluation/main.py generation --limit 5               # real LLM (5 × 4 calls = 20 calls)
```
Each row: `F=faithfulness R=relevance C=correctness` (1-5) + the answer. Averages on the last line.

## 3. Offline tests
```bash
pytest 04-rag/06-rag-evaluation -v
```
| Test | What it proves |
|---|---|
| `test_metric_math` | hit/RR/recall formulas |
| `test_evaluate_retrieval_with_fake_retriever` | duplicate sources deduped, failures list |
| `test_compare_configs_on_real_data` | raising k does not lower hit/recall |
| `test_judge_validates_score_range` | judge returned 9 → rejected → retry |
| `test_generation_eval_offline` | the full generation eval loop |
| `test_offline_judge_penalises_unfaithful_answer` | a hallucinated answer scores lower |

## What to look for
- Which config is best, and **why**? Chunk count vs MRR.
- The `miss:` lines: why did retrieval fail on these questions? Debug with `01-rag-basics --show-chunks`.
- In generation: which answers are faithful but irrelevant (F high, R low)?

## Tinker with it
1. **Your own config**: add `RetrievalConfig("fixed-50/k5", "fixed", 50, 10, 5)` to `CONFIGS`. What happens with very small chunks?
2. **Hard questions**: add 5 vocabulary-mismatch questions to the eval set ("How do I get my money back on a card?"). Measure the difference between the local and a real embedder.
3. **Unanswerable**: add `{"question": "Do you sell cars?", "relevant_sources": []}` and change `evaluate_retrieval` so that "IDK was correct" gets counted.
4. Write **Precision@k** and **nDCG** functions and add columns for them to the table.
5. **Hybrid compare**: plug `03-hybrid-search-rerank`'s `HybridRetriever` into `evaluate_retrieval` (`retrieve` is just a function).
6. **Judge audit**: score 10 of the real judge's cases yourself by hand. How many matched? What would you change in the rubric?
