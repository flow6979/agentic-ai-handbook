# Agentic RAG: kaise chalayein, test karein, tinker karein

Setup: repo root se `source .venv/bin/activate && pip install -e ".[all]"`.
Data: `data/hr/*.md` (employee policies) aur `data/product/*.md` (customer policies) = 2 knowledge bases.

## 1. Corrective pipeline offline (trace dekho)
```bash
P=04-rag/05-agentic-rag/main.py
python $P "How many sick leave days do employees get?" --offline
python $P "What is the refund window and how many sick leave days do employees get?" --offline
python $P "How many vacation days do I get?" --offline         # rewrite path
python $P "hello there" --offline                              # no retrieval
python $P "Can I bring my dog to office?" --offline            # not found
```
Vacation wale ka expected trace:
```
  - route -> ['hr'] (keyword match)
  - sub-questions -> ['How many vacation days do I get?']
  - retrieve('How many vacation days do I get?') -> 4 candidates, 0 relevant
  - rewrite -> 'how many paid leave days do i get?'
  - retrieve('how many paid leave days do i get?') -> 4 candidates, 2 relevant
  - groundedness -> True
```
Note: offline "LLM" rule-based hai (keywords + synonyms table), isliye uske answers crude hain. Pipeline
ka flow (kaunsa step kab chala) asli hai.

## 2. Tool-calling agent mode
```bash
python $P "What is the hotel cap per night for employees?" --mode agent --offline
python $P "Compare the refund window with the notice period after confirmation" --mode agent   # real LLM: 2 searches?
```
Colored trace mein `search_hr(...)` / `search_product(...)` calls dikhenge.

## 3. Real LLM
`.env` mein `LLM_MODEL` set karke upar ke commands bina `--offline` chalao. Dekho:
- Router kya choose karta hai "Is express shipping free for employees?" pe (dono KBs?)
- Rewrite kaisa likhta hai
- Groundedness checker kabhi false deta hai?

## 4. Offline tests
```bash
pytest 04-rag/05-agentic-rag -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_search_tool_schema_and_results` | KB → tool conversion |
| `test_routes_to_single_kb` | hr routing + grounded answer |
| `test_multi_part_question_decomposed_across_kbs` | 2 sub-questions, 2 KBs |
| `test_no_retrieval_for_chitchat` | sirf 2 LLM calls |
| `test_rewrite_rescues_vocabulary_mismatch` | vacation → paid leave |
| `test_not_found_when_grader_rejects_everything` | honest "not found" |
| `test_ungrounded_answer_is_regenerated_then_flagged` | unknown KB ignore, bad indices ignore, regenerate with feedback |
| `test_tool_calling_agent_decides_to_search` | agent ne sahi tool choose kiya |
| `test_agent_can_search_multiple_times` | multi-tool-call loop |

## Tinker karo
1. **LLM calls gino**: `ScriptedLLM(offline_agentic_llm)` ka `len(llm.calls)` har sawaal ke baad print karo. Kaunsa step sabse mehenga hai? Kaunsa skip kar sakte ho?
2. **HyDE**: `_retrieve_graded` mein pehle LLM se "hypothetical answer" likhwao aur use search query banao. Real LLM + real embeddings pe vacation wala case compare karo.
3. **Embedding router**: `Route` LLM call ki jagah query ko har KB ke `description` se cosine compare karke route karo. Accuracy vs LLM router?
4. **Security**: ek `customer_mode=True` flag banao jisme `hr` KB router ko dikhe hi nahi. "What's the employee hotel cap?" pe kya hota hai?
5. **Web fallback**: "not found" ki jagah `03-web-agents` ka search tool call karo (true CRAG).
6. **Grader strictness**: offline grader `>= 2` overlap maangta hai; `>= 1` karo aur dekho kitna noise answer mein aata hai.
