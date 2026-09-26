**Language:** Hinglish · [English](TESTING.en.md)

# RAG Evaluation: kaise chalayein, test karein, tinker karein

Setup: repo root se `source .venv/bin/activate && pip install -e ".[all]"`.

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
Real embedder ke saath: `EMBED_MODEL=gemini:text-embedding-004 python ... retrieval`, numbers compare karo.

## 2. Generation eval
```bash
python 04-rag/06-rag-evaluation/main.py generation --offline --limit 4     # fake answerer + fake judge
python 04-rag/06-rag-evaluation/main.py generation --limit 5               # real LLM (5 × 4 calls = 20 calls)
```
Har row: `F=faithfulness R=relevance C=correctness` (1-5) + answer. Last line pe averages.

## 3. Offline tests
```bash
pytest 04-rag/06-rag-evaluation -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_metric_math` | hit/RR/recall formulas |
| `test_evaluate_retrieval_with_fake_retriever` | duplicate sources dedupe, failures list |
| `test_compare_configs_on_real_data` | k badhane se hit/recall kam nahi hota |
| `test_judge_validates_score_range` | judge ne 9 diya → reject → retry |
| `test_generation_eval_offline` | poora generation eval loop |
| `test_offline_judge_penalises_unfaithful_answer` | hallucinated answer ka score kam |

## Kya dekhna hai
- Kaunsa config best hai aur **kyun**? Chunks count vs MRR.
- `miss:` lines: in sawaalon pe retrieval kyun fail hua? `01-rag-basics --show-chunks` se debug karo.
- Generation mein: faithful lekin irrelevant answers (F high, R low) kaun se hain?

## Tinker karo
1. **Apna config**: `CONFIGS` mein `RetrievalConfig("fixed-50/k5", "fixed", 50, 10, 5)` jodo. Bahut chhote chunks pe kya hota hai?
2. **Hard questions**: eval set mein 5 vocabulary-mismatch sawaal jodo ("How do I get my money back on a card?"). Local vs real embedder ka fark naapo.
3. **Unanswerable**: `{"question": "Do you sell cars?", "relevant_sources": []}` jodo aur `evaluate_retrieval` ko aisa banao ki "IDK sahi tha" count ho.
4. **Precision@k** aur **nDCG** functions likho aur table mein column jodo.
5. **Hybrid compare**: `03-hybrid-search-rerank` ke `HybridRetriever` ko `evaluate_retrieval` mein plug karo (`retrieve` bas ek function hai).
6. **Judge audit**: real judge ke 10 scores khud manually score karo. Kitne match hue? Rubric mein kya badloge?
