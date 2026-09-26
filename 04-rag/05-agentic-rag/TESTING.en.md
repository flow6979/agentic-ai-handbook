**Language:** [Hinglish](TESTING.md) · English

# Agentic RAG: how to run, test and tinker

Setup: from the repo root, `source .venv/bin/activate && pip install -e ".[all]"`.
Data: `data/hr/*.md` (employee policies) and `data/product/*.md` (customer policies) = 2 knowledge bases.

## 1. Corrective pipeline offline (watch the trace)
```bash
P=04-rag/05-agentic-rag/main.py
python $P "How many sick leave days do employees get?" --offline
python $P "What is the refund window and how many sick leave days do employees get?" --offline
python $P "How many vacation days do I get?" --offline         # rewrite path
python $P "hello there" --offline                              # no retrieval
python $P "Can I bring my dog to office?" --offline            # not found
```
Expected trace for the vacation question:
```
  - route -> ['hr'] (keyword match)
  - sub-questions -> ['How many vacation days do I get?']
  - retrieve('How many vacation days do I get?') -> 4 candidates, 0 relevant
  - rewrite -> 'how many paid leave days do i get?'
  - retrieve('how many paid leave days do i get?') -> 4 candidates, 2 relevant
  - groundedness -> True
```
Note: the offline "LLM" is rule-based (keywords + a synonyms table), so its answers are crude. The pipeline's
flow (which step ran when) is real.

## 2. Tool-calling agent mode
```bash
python $P "What is the hotel cap per night for employees?" --mode agent --offline
python $P "Compare the refund window with the notice period after confirmation" --mode agent   # real LLM: 2 searches?
```
The colored trace shows the `search_hr(...)` / `search_product(...)` calls.

## 3. Real LLM
Set `LLM_MODEL` in `.env` and run the commands above without `--offline`. Watch:
- What the router chooses for "Is express shipping free for employees?" (both KBs?)
- How it writes the rewrite
- Does the groundedness checker ever return false?

## 4. Offline tests
```bash
pytest 04-rag/05-agentic-rag -v
```
| Test | What it proves |
|---|---|
| `test_search_tool_schema_and_results` | KB → tool conversion |
| `test_routes_to_single_kb` | hr routing + grounded answer |
| `test_multi_part_question_decomposed_across_kbs` | 2 sub-questions, 2 KBs |
| `test_no_retrieval_for_chitchat` | only 2 LLM calls |
| `test_rewrite_rescues_vocabulary_mismatch` | vacation → paid leave |
| `test_not_found_when_grader_rejects_everything` | honest "not found" |
| `test_ungrounded_answer_is_regenerated_then_flagged` | unknown KB ignored, bad indices ignored, regenerate with feedback |
| `test_tool_calling_agent_decides_to_search` | the agent chose the right tool |
| `test_agent_can_search_multiple_times` | multi-tool-call loop |

## Tinker with it
1. **Count LLM calls**: print `len(llm.calls)` of `ScriptedLLM(offline_agentic_llm)` after each question. Which step is the most expensive? Which can you skip?
2. **HyDE**: in `_retrieve_graded`, first have the LLM write a "hypothetical answer" and use it as the search query. Compare the vacation case with a real LLM + real embeddings.
3. **Embedding router**: instead of the `Route` LLM call, route by comparing the query's cosine with each KB's `description`. Accuracy vs the LLM router?
4. **Security**: add a `customer_mode=True` flag where the `hr` KB is never shown to the router. What happens for "What's the employee hotel cap?"?
5. **Web fallback**: instead of "not found", call the search tool from `03-web-agents` (true CRAG).
6. **Grader strictness**: the offline grader requires `>= 2` overlap; change it to `>= 1` and see how much noise gets into the answer.
