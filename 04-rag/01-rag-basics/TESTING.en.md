**Language:** [Hinglish](TESTING.md) · English

# RAG Basics: how to run, test and tinker

## Setup (from the repo root, once)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # fill LLM_MODEL + one API key (or ollama)
```

## 1. Run without a key (offline)
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
In `--offline` the LLM is fake (`offline_answerer`): it copies the best-matching sentence from the context.
Retrieval, the prompt and citations are all the real pipeline.

## 2. With a real LLM
```bash
python 04-rag/01-rag-basics/main.py "Can I cancel a yearly Plus plan after a month?" --show-chunks
python 04-rag/01-rag-basics/main.py "What is the capital of France?"      # to see the refusal path
```
For real embeddings set `EMBED_MODEL=gemini:text-embedding-004` (or `ollama:nomic-embed-text`) in `.env`.

## 3. Compare the chunkers
```bash
python 04-rag/01-rag-basics/main.py --compare-chunkers --size 200
```

## 4. Offline tests
```bash
pytest 04-rag/01-rag-basics -v
```
| Test | What it proves |
|---|---|
| `test_fixed_chunks_overlap` | overlap is correct, size limit is followed |
| `test_recursive_respects_size_and_hard_cuts_long_words` | splits on paragraphs + hard cut for a long word |
| `test_sentence_chunker_never_splits_sentence` | sentence integrity |
| `test_retrieval_finds_right_doc` | refund question → refund doc is top-1 |
| `test_answer_has_citation_and_context_in_prompt` | prompt contains CONTEXT/QUESTION + only retrieved docs are cited |
| `test_idk_without_calling_llm_when_nothing_relevant` | min_score gate: the LLM was not called at all |

## What to look for
- Scores from `--show-chunks`: is the right doc at the top? How big is the gap between the first and second score?
- Refusal: does an irrelevant question get "I don't know", or does the LLM guess?
- Citations: are the answer's `[source]` values only from the retrieved chunks?

## Tinker with it
1. **Chunk size**: ask "How much does Express shipping cost?" with `--size 120` vs `--size 1000`. How do the retrieved chunk and the answer change?
2. **Remove overlap**: set `chunk_fixed(..., overlap=0)` and see which sentences break at the boundary.
3. **Threshold**: set `RAG(min_score=0.3)`. Which correct questions now get "I don't know"? What does the cricket question do at `0.0`?
4. **Prompt**: remove "ONLY the context" from `SYSTEM_PROMPT` and ask a real LLM "What is the capital of France?". Did hallucination/outside knowledge come back?
5. **Your own data**: point `--data ~/notes` at your markdown notes and ask questions.
6. **Contextual headers**: in `chunk_documents`, prefix each chunk with `f"{d.id}: "` (title prefix). Did retrieval improve for chunks like "It costs 99 rupees"?
