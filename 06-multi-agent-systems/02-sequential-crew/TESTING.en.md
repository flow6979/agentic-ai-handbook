**Language:** [Hinglish](TESTING.md) · English

# 02 · Sequential Crew: Test & Tinker

## Run

```bash
# offline (fake LLM): QA fails the first time, the developer fixes it
python 06-multi-agent-systems/02-sequential-crew/main.py --offline

# real LLM
python 06-multi-agent-systems/02-sequential-crew/main.py "a password strength checker function"

# a different model for each role
LLM_MODEL_DEVELOPER=openai:gpt-4o-mini LLM_MODEL_QA=anthropic:claude-sonnet-5 \
  python 06-multi-agent-systems/02-sequential-crew/main.py "a slugify(text) helper"
```

Expected (offline): `STORIES`, `DESIGN`, `CODE`, `QA` sections, then `FILES (1)` containing `calc.py` with a `TypeError` check, and `QA passed=True after 1 rework(s)`.

## Tests

```bash
pytest 06-multi-agent-systems/02-sequential-crew -v
```

| Test | What it proves |
|---|---|
| `test_full_pipeline_with_one_rework` | 4 stages + 1 rework, and the final file is fixed |
| `test_no_rework_when_qa_passes` | No extra work happens when QA passes |
| `test_context_passing_only_declared_dependencies` | Each role only gets the outputs declared in its context |
| `test_rework_budget_stops_endless_qa_failures` | The loop stops even if QA always fails |
| `test_each_role_gets_its_own_llm` | The per-role LLM factory is called |

## What to look for in traces

Each role has its own tracer name: `[pm:info]`, `[architect:result]`, `[developer:tool] save_file({...})`. The Developer's trace should show the tool call and `-> saved calc.py`. With a real LLM, check whether the Architect actually follows the "file list + signatures" format.

## Tinker 🔧

1. **A new stage**: add `Task("docs", "Write README", "Markdown README", tech_writer_role, context=["design","code"])` after the Developer.
2. **Context bleeding experiment**: set the Developer task's `context` to just `["stories"]` (drop design). Does the code structure get worse?
3. **Give QA a tool**: build a `run_python(code)` tool that `exec`s the code and runs asserts (in a sandbox only!). Then QA works from real test results instead of the LLM's opinion.
4. **`max_reworks=0`**: see how often a real LLM passes QA on the first try.
5. **Human checkpoint**: add `input("approve design? y/n")` after the `design` stage. That is the simplest form of human-in-the-loop.
6. **Measure cost**: collect `AgentResult.usage` from `Agent.run()` and print each role's tokens. Which role is the most expensive?
