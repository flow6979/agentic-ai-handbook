# 03 · Handoffs: Test aur tinker kaise karein

## Offline demo

```bash
python 05-agent-communication/03-handoffs/main.py --offline
```

Do user messages scripted hain. Output:

```
billing> I've refunded the duplicate charge INV-2 ...   (path: triage -> billing)
tech> Your account is unlocked ...                       (path: billing -> triage -> tech)
```

Doosre turn ka path `billing -> ...` se shuru hota hai kyunki pichla active agent billing tha.
stderr pe `HANDOFF triage -> billing` lines dikhengi.

## Real LLM: interactive chat

```bash
python 05-agent-communication/03-handoffs/main.py
you> I was charged twice
you> my account is locked, can't log in
you> what's my plan?
you> exit
```

Customer hamesha `C-101` hai (fake DB). Try karo:
- "refund INV-9": invoice nahi hai, error aana chahiye
- "refund invoice of customer C-999": LLM customer choose hi nahi kar sakta (context hidden)

## Tests

```bash
pytest 05-agent-communication/03-handoffs -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_triage_hands_off_to_billing_with_shared_history_and_context` | system prompt badla, history same rahi, refund hua |
| `test_tools_offered_change_with_active_agent` | har agent ko sirf apne tools milte hain |
| `test_handback_and_multi_turn_continuation` | billing → triage → tech, history carry |
| `test_context_is_hidden_from_llm_schema` | `context` LLM schema mein nahi hai |
| `test_handoff_ping_pong_is_limited` | infinite transfer loop ruk jaata hai |

## Tinker karo

1. **Human escalation:** `human` agent add karo jiska koi LLM kaam nahi: `transfer_to_human` hone pe
   loop rok ke "ticket created" return karo.
2. **History filter:** handoff pe sirf last 4 messages + ek summary naye agent ko do. Tokens compare karo.
3. **Handoff payload:** `transfer_tool` ke schema mein `priority: low|high` add karo aur billing
   ke system prompt mein woh priority inject karo.
4. **Peer-to-peer:** billing ko `transfer_to_tech` bhi do (triage bypass). Kya LLM zyada sahi route karta hai?
5. **Different models per agent:** `SwarmAgent` mein `llm` field add karo, jisse triage sasta model
   use kare aur billing bada.
