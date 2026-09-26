**Language:** [Hinglish](TESTING.md) · English

# 04 · Hierarchical Teams: Test & Tinker

## Run

```bash
python 06-multi-agent-systems/04-hierarchical-teams/main.py --offline
python 06-multi-agent-systems/04-hierarchical-teams/main.py "Launch a budgeting app for college students"
# strong top, cheap leaves
LLM_MODEL_MANAGER=gemini:gemini-2.5-pro LLM_MODEL=groq:llama-3.1-8b-instant \
  python 06-multi-agent-systems/04-hierarchical-teams/main.py "Launch an AI note-taking app"
```

Expected (offline): `MARKETING TEAM` (copywriter and social_media outputs + team report), `ENGINEERING TEAM` (backend_dev, qa_engineer + report), and `FINAL LAUNCH PLAN`.

## Tests

```bash
pytest 06-multi-agent-systems/04-hierarchical-teams -v
```

| Test | What it proves |
|---|---|
| `test_two_levels_roll_up` | All workers in both teams ran and the final plan was built |
| `test_manager_sees_only_team_summaries_not_raw_worker_output` | Roll-up: raw worker output never reaches the manager |
| `test_hallucinated_team_and_worker_are_skipped` | The invented "legal" team / "designer" worker are skipped + recorded |
| `test_role_keys_for_per_level_models` | The LLM for each level is requested with the right role key |

## What to look for in traces

Tracer names like `marketing.copywriter` and `engineering.qa_engineer` show the hierarchy. With a real LLM, watch for the `(skipped invalid names: [...])` line: does the model invent extra teams?

## Tinker 🔧

1. **A third team**: add `TEAMS["support"] = {"faq_writer": ..., "trainer": ...}`. The manager prompt updates itself (`', '.join(TEAMS)`).
2. **Parallel teams**: run the teams in parallel with a `ThreadPoolExecutor` inside `LaunchManager.run()` and compare the time.
3. **Telephone game test**: put a critical risk into one worker's output ("API rate limit blocks launch"). Does it make it into the final plan? If not, make a "Risks:" line mandatory in the team report format.
4. **Escalation**: if a worker's output starts with "BLOCKED:", the lead should escalate it to the manager. Implement it.
5. **Dynamic teams**: remove `TEAMS` and have the manager generate the team + worker roles itself (risky, see what happens).
