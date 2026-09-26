**Language:** [Hinglish](TESTING.md) · English

# 03 · Handoffs: how to test and tinker

## Offline demo

```bash
python 05-agent-communication/03-handoffs/main.py --offline
```

Two user messages are scripted. Output:

```
billing> I've refunded the duplicate charge INV-2 ...   (path: triage -> billing)
tech> Your account is unlocked ...                       (path: billing -> triage -> tech)
```

The second turn's path starts with `billing -> ...` because the previous active agent was billing.
You will see `HANDOFF triage -> billing` lines on stderr.

## Real LLM: interactive chat

```bash
python 05-agent-communication/03-handoffs/main.py
you> I was charged twice
you> my account is locked, can't log in
you> what's my plan?
you> exit
```

The customer is always `C-101` (fake DB). Try:
- "refund INV-9": the invoice does not exist, so you should get an error
- "refund invoice of customer C-999": the LLM cannot pick the customer at all (context is hidden)

## Tests

```bash
pytest 05-agent-communication/03-handoffs -v
```

| Test | What it proves |
|---|---|
| `test_triage_hands_off_to_billing_with_shared_history_and_context` | the system prompt changed, the history stayed the same, the refund happened |
| `test_tools_offered_change_with_active_agent` | each agent gets only its own tools |
| `test_handback_and_multi_turn_continuation` | billing → triage → tech, history carried over |
| `test_context_is_hidden_from_llm_schema` | `context` is not in the LLM schema |
| `test_handoff_ping_pong_is_limited` | an infinite transfer loop gets stopped |

## Tinker with it

1. **Human escalation:** add a `human` agent that does no LLM work: when `transfer_to_human` happens,
   stop the loop and return "ticket created".
2. **History filter:** on handoff, give the new agent only the last 4 messages + a summary. Compare tokens.
3. **Handoff payload:** add `priority: low|high` to the `transfer_tool` schema and inject that priority
   into billing's system prompt.
4. **Peer-to-peer:** give billing `transfer_to_tech` too (bypassing triage). Does the LLM route more accurately?
5. **Different models per agent:** add an `llm` field to `SwarmAgent` so triage uses a cheap model
   and billing a bigger one.
