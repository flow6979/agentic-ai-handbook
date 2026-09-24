# 02 · Sequential Crew — Test & Tinker

## Run

```bash
# offline (fake LLM): QA pehli baar fail karega, developer fix karega
python 06-multi-agent-systems/02-sequential-crew/main.py --offline

# real LLM
python 06-multi-agent-systems/02-sequential-crew/main.py "a password strength checker function"

# alag model har role ke liye
LLM_MODEL_DEVELOPER=openai:gpt-4o-mini LLM_MODEL_QA=anthropic:claude-sonnet-5 \
  python 06-multi-agent-systems/02-sequential-crew/main.py "a slugify(text) helper"
```

Expected (offline): `STORIES`, `DESIGN`, `CODE`, `QA` sections, phir `FILES (1)` mein `calc.py` jisme `TypeError` check hai, aur `QA passed=True after 1 rework(s)`.

## Tests

```bash
pytest 06-multi-agent-systems/02-sequential-crew -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_full_pipeline_with_one_rework` | 4 stages + 1 rework, final file fixed hai |
| `test_no_rework_when_qa_passes` | QA pass ho to extra kaam nahi hota |
| `test_context_passing_only_declared_dependencies` | Har role ko sirf uske declared context outputs milte hain |
| `test_rework_budget_stops_endless_qa_failures` | QA hamesha fail kare tab bhi loop ruk jaata hai |
| `test_each_role_gets_its_own_llm` | Per-role LLM factory call hoti hai |

## Traces mein kya dekhna hai

Har role ka apna tracer naam hai: `[pm:info]`, `[architect:result]`, `[developer:tool] save_file({...})`. Developer ke trace mein tool call aur `-> saved calc.py` dikhna chahiye. Real LLM pe dekho ki kya Architect sach mein "file list + signatures" format follow karta hai.

## Tinker karo 🔧

1. **Naya stage**: `Task("docs", "Write README", "Markdown README", tech_writer_role, context=["design","code"])` add karo, Developer ke baad.
2. **Context bleeding experiment**: Developer task ka `context` mein sirf `["stories"]` rakho (design hata do). Kya code ka structure bigadta hai?
3. **QA ko tool do**: ek `run_python(code)` tool banao jo `exec` karke asserts chalaye (sirf sandbox mein!). Isse QA LLM ki raay ki jagah asli test result pe chalega.
4. **`max_reworks=0`**: dekho kitni baar real LLM pehli koshish mein QA pass karta hai.
5. **Human checkpoint**: `design` stage ke baad `input("approve design? y/n")` daalo. Yahi human-in-the-loop ka simplest roop hai.
6. **Cost measure karo**: `Agent.run()` ka `AgentResult.usage` collect karke har role ke tokens print karo. Kaunsa role sabse mehnga hai?
