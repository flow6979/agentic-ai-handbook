# 04 · Hierarchical Teams — Test & Tinker

## Run

```bash
python 06-multi-agent-systems/04-hierarchical-teams/main.py --offline
python 06-multi-agent-systems/04-hierarchical-teams/main.py "Launch a budgeting app for college students"
# strong top, cheap leaves
LLM_MODEL_MANAGER=gemini:gemini-2.5-pro LLM_MODEL=groq:llama-3.1-8b-instant \
  python 06-multi-agent-systems/04-hierarchical-teams/main.py "Launch an AI note-taking app"
```

Expected (offline): `MARKETING TEAM` (copywriter, social_media outputs + team report), `ENGINEERING TEAM` (backend_dev, qa_engineer + report), aur `FINAL LAUNCH PLAN`.

## Tests

```bash
pytest 06-multi-agent-systems/04-hierarchical-teams -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_two_levels_roll_up` | Dono teams ke saare workers chale, final plan bana |
| `test_manager_sees_only_team_summaries_not_raw_worker_output` | Roll-up: manager ko raw worker output nahi jaata |
| `test_hallucinated_team_and_worker_are_skipped` | Invented "legal" team / "designer" worker skip + record |
| `test_role_keys_for_per_level_models` | Har level ke liye sahi role key se LLM maanga gaya |

## Traces mein kya dekhna hai

Tracer names `marketing.copywriter`, `engineering.qa_engineer` hierarchy dikhate hain. Real LLM pe `(skipped invalid names: [...])` line pe nazar rakho: kya model extra teams invent karta hai?

## Tinker karo 🔧

1. **Teesri team**: `TEAMS["support"] = {"faq_writer": ..., "trainer": ...}` add karo. Manager prompt apne aap update ho jaata hai (`', '.join(TEAMS)`).
2. **Parallel teams**: `LaunchManager.run()` mein teams ko `ThreadPoolExecutor` se parallel chalao aur time compare karo.
3. **Telephone game test**: kisi worker ke output mein ek critical risk daalo ("API rate limit blocks launch"). Kya woh final plan tak pahunchta hai? Agar nahi, to team report format mein "Risks:" line mandatory karo.
4. **Escalation**: worker agar "BLOCKED:" se start kare to lead usse manager ko escalate kare. Implement karo.
5. **Dynamic teams**: `TEAMS` hata ke manager se hi team + worker roles generate karwao (risky, dekho kya hota hai).
