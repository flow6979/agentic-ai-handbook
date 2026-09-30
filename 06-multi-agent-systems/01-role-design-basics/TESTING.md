**Language:** Hinglish · [English](TESTING.en.md)

# 01 · Role Design Basics — Test & Tinker

## Setup (repo root se, ek baar)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # ek provider ki key bharo (Groq/Gemini free tier chal jaata hai)
```

## 1. Offline run (bina key)

```bash
python 06-multi-agent-systems/01-role-design-basics/main.py --offline --show-prompts
```

Expected: pehle dono roles ke generated system prompts print honge. Phir `[Writer]` → `[Editor] approved:false` → `[Writer]` (revised, "menu" example) → `[Editor] approved:true`, aur end mein `FINAL (after 2 editor round(s))`.

## 2. Real LLM ke saath

```bash
python 06-multi-agent-systems/01-role-design-basics/main.py "What is Docker?" --show-prompts
# alag models per role:
LLM_MODEL_WRITER=groq:llama-3.1-8b-instant LLM_MODEL_EDITOR=gemini:gemini-3.8-flash \
  python 06-multi-agent-systems/01-role-design-basics/main.py "What is Kubernetes?"
```

## 3. Offline tests

```bash
pytest 06-multi-agent-systems/01-role-design-basics -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_system_prompt_has_all_role_parts` | Template mein saare role hisse aate hain |
| `test_minimal_role_prompt_skips_empty_sections` | Khaali fields prompt ganda nahi karte |
| `test_writer_editor_revises_once_then_approves` | Poora revise loop sahi order mein chalta hai |
| `test_revision_budget_terminates_even_if_never_approved` | Editor kabhi approve na kare tab bhi loop rukta hai |
| `test_per_role_llm_factory_receives_role_names` | Har role ke liye alag LLM maanga jaata hai |

## Traces mein kya dekhna hai

`AGENT_VERBOSE=1` (default) pe stderr mein `[writer:info] task: ...` aur `[writer:result] ...` dikhega. Editor `llm_json` se chalta hai (agent loop nahi), isliye uska output `[Editor]` history mein dikhta hai. `AGENT_TRACE_FILE=traces.jsonl` set karo to saare events JSONL mein save ho jaate hain.

## Tinker karo 🔧

1. **Role drift dekho**: `EDITOR.forbidden_actions` hata do aur real LLM se chalao. Kya editor khud poora article likhne lagta hai?
2. **Vague role**: `write_with_editor` mein WRITER ki jagah `BAD_ROLE` use karo. Output ki length aur focus compare karo.
3. **Teesra role add karo**: ek `FACT_CHECKER` role banao jo Editor se pehle claims verify kare, output `{"claims_ok": bool, "problems": [...]}`.
4. **Strict editor**: goal mein "under 60 words" kar do aur `max_revisions=0/1/3` pe dekho kitne rounds lagte hain.
5. **Cheap vs strong**: writer ko chhota model (8B) aur editor ko bada model do, phir ulta karke dekho. Quality mein kya farq aata hai?
6. **Output contract todo**: editor ke `output_contract` se JSON hata do. `llm_json` ka self-correction retry dikhega (aur kabhi kabhi fail bhi hoga).
