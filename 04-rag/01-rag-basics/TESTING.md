**Language:** Hinglish · [English](TESTING.en.md)

# RAG Basics: kaise chalayein, test karein, tinker karein

## Setup (repo root se, ek baar)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # LLM_MODEL + ek API key bharo (ya ollama)
```

## 1. Bina key ke (offline) chalao
```bash
python 04-rag/01-rag-basics/main.py "How long do card refunds take?" --offline --show-chunks
```
Expected:
```
--- retrieved ---
0.275  refund_policy.md#1     '## Non-refundable items...'
...
Card refunds take 5 to 7 business days. [refund_policy.md]
sources: ['refund_policy.md']
```
`--offline` mein LLM nakli hai (`offline_answerer`): woh context ka best-matching sentence copy karta hai.
Retrieval, prompt, citations sab asli pipeline hai.

## 2. Real LLM ke saath
```bash
python 04-rag/01-rag-basics/main.py "Can I cancel a yearly Plus plan after a month?" --show-chunks
python 04-rag/01-rag-basics/main.py "What is the capital of France?"      # refusal path dekhna hai
```
Real embeddings ke liye `.env` mein `EMBED_MODEL=gemini:text-embedding-004` (ya `ollama:nomic-embed-text`).

## 3. Chunkers compare karo
```bash
python 04-rag/01-rag-basics/main.py --compare-chunkers --size 200
```

## 4. Offline tests
```bash
pytest 04-rag/01-rag-basics -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_fixed_chunks_overlap` | overlap sahi, size limit follow |
| `test_recursive_respects_size_and_hard_cuts_long_words` | paragraph pe katna + lambe word ka hard cut |
| `test_sentence_chunker_never_splits_sentence` | sentence integrity |
| `test_retrieval_finds_right_doc` | refund question → refund doc top-1 |
| `test_answer_has_citation_and_context_in_prompt` | prompt mein CONTEXT/QUESTION + sirf retrieved docs cite |
| `test_idk_without_calling_llm_when_nothing_relevant` | min_score gate: LLM call hi nahi hua |

## Kya dekhna hai
- `--show-chunks` ke scores: sahi doc top pe hai? Doosre aur pehle score mein gap kitna hai?
- Refusal: irrelevant question pe "I don't know" aata hai ya LLM guess karta hai?
- Citations: answer ke `[source]` retrieved chunks mein se hi hain?

## Tinker karo
1. **Chunk size**: `--size 120` vs `--size 1000` se "Express shipping kitne ka hai?" poochho. Retrieved chunk aur answer kaise badle?
2. **Overlap hatao**: `chunk_fixed(..., overlap=0)` karke dekho kaunse sentences boundary pe toot rahe hain.
3. **Threshold**: `RAG(min_score=0.3)` karo. Kaunse sahi sawaal ab "I don't know" dene lage? `0.0` pe cricket wala sawaal kya karta hai?
4. **Prompt**: `SYSTEM_PROMPT` se "ONLY the context" hata do aur real LLM se "What is the capital of France?" poochho. Hallucination/outside-knowledge wapas aa gaya?
5. **Apna data**: `--data ~/notes` pe apne markdown notes daalo aur sawaal poochho.
6. **Contextual headers**: `chunk_documents` mein har chunk ke aage `f"{d.id}: "` jod do (title prefix). "It costs 99 rupees" type chunks ki retrieval sudhri?
