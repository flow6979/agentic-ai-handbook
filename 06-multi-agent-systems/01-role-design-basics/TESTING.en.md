**Language:** [Hinglish](TESTING.md) · English

# 01 · Role Design Basics: Test & Tinker

## Setup (once, from the repo root)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # fill in one provider's key (Groq/Gemini free tier works)
```

## 1. Offline run (no key)

```bash
python 06-multi-agent-systems/01-role-design-basics/main.py --offline --show-prompts
```

Expected: first the generated system prompts for both roles are printed. Then `[Writer]` → `[Editor] approved:false` → `[Writer]` (revised, the "menu" example) → `[Editor] approved:true`, and finally `FINAL (after 2 editor round(s))`.

## 2. With a real LLM

```bash
python 06-multi-agent-systems/01-role-design-basics/main.py "What is Docker?" --show-prompts
# different models per role:
LLM_MODEL_WRITER=groq:llama-3.1-8b-instant LLM_MODEL_EDITOR=gemini:gemini-3.8-flash \
  python 06-multi-agent-systems/01-role-design-basics/main.py "What is Kubernetes?"
```

## 3. Offline tests

```bash
pytest 06-multi-agent-systems/01-role-design-basics -v
```

| Test | What it proves |
|---|---|
| `test_system_prompt_has_all_role_parts` | Every part of the role appears in the template |
| `test_minimal_role_prompt_skips_empty_sections` | Empty fields don't clutter the prompt |
| `test_writer_editor_revises_once_then_approves` | The whole revise loop runs in the right order |
| `test_revision_budget_terminates_even_if_never_approved` | The loop stops even if the editor never approves |
| `test_per_role_llm_factory_receives_role_names` | A separate LLM is requested for each role |

## What to look for in traces

With `AGENT_VERBOSE=1` (the default) you will see `[writer:info] task: ...` and `[writer:result] ...` on stderr. The Editor runs through `llm_json` (not the agent loop), so its output shows up in the `[Editor]` history. Set `AGENT_TRACE_FILE=traces.jsonl` to save every event as JSONL.

## Tinker 🔧

1. **Watch role drift**: remove `EDITOR.forbidden_actions` and run with a real LLM. Does the editor start writing the whole article itself?
2. **Vague role**: use `BAD_ROLE` instead of WRITER in `write_with_editor`. Compare the length and focus of the output.
3. **Add a third role**: create a `FACT_CHECKER` role that verifies claims before the Editor, with output `{"claims_ok": bool, "problems": [...]}`.
4. **Strict editor**: change the goal to "under 60 words" and see how many rounds it takes with `max_revisions=0/1/3`.
5. **Cheap vs strong**: give the writer a small model (8B) and the editor a big one, then swap them. What changes in quality?
6. **Break the output contract**: remove the JSON from the editor's `output_contract`. You will see `llm_json`'s self-correction retry (and sometimes a failure).
