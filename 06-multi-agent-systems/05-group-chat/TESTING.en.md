**Language:** [Hinglish](TESTING.md) · English

# 05 · Group Chat: Test & Tinker

## Run

```bash
# compare all three selectors offline
python 06-multi-agent-systems/05-group-chat/main.py --offline --selector round_robin
python 06-multi-agent-systems/05-group-chat/main.py --offline --selector rules
python 06-multi-agent-systems/05-group-chat/main.py --offline --selector llm

# real LLM
python 06-multi-agent-systems/05-group-chat/main.py "Plan a 2-day Jaipur trip under INR 15,000" --selector llm --max-turns 8
```

Expected (offline): the transcript is printed, ending with `[stopped: consensus after 6 turns ...]` (7 turns with the rules selector, because the `@planner` mention changes the order).

## Tests

```bash
pytest 06-multi-agent-systems/05-group-chat -v
```

| Test | What it proves |
|---|---|
| `test_llm_selector_reaches_consensus` | The LLM selector flow and consensus termination |
| `test_round_robin_order` | Fixed order |
| `test_rule_based_mention_and_keywords` | `@mention` > keywords > fallback (skip the last speaker) |
| `test_llm_selector_falls_back_on_invalid_name` | Hallucinated speaker → round-robin fallback |
| `test_terminate_keyword_and_max_turns` | Both termination paths |
| `test_every_participant_sees_shared_transcript` | The shared context really is shared |

## What to look for in traces

The `[groupchat:llm] budget_keeper: ...` lines include the turn number. With a real LLM, check:
- Does consensus actually happen, or does the chat get cut off at `max_turns`?
- Is the LLM selector picking one participant too often?

## Tinker 🔧

1. **Devil's advocate**: add a `skeptic` participant that always looks for risks. Does consensus come later? Is the plan better?
2. **Sliding window**: send only the last 6 messages in `Participant.speak()` and compare token usage.
3. Write a **random selector**, and add a **fairness rule** (nobody speaks twice in a row).
4. **A human in the chat**: create a `Participant` whose `speak()` comes from `input()`. Now you're in the group too!
5. **Consensus vs keyword**: add "say TERMINATE when final" to the planner prompt. Which one triggers first?
6. **Mixed models**: planner = a big model, everyone else = a small model. Compare the quality of the transcript.
