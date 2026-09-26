**Language:** Hinglish · [English](TESTING.en.md)

# 07 · Swarm & Handoffs — Test & Tinker

## Run

```bash
# interactive offline chat
python 06-multi-agent-systems/07-swarm-handoffs/main.py --offline
#   you> where is my order A200?
#   you> my wifi router is not working
#   you> I want a refund for order A100
#   you> exit

# one-shot
python 06-multi-agent-systems/07-swarm-handoffs/main.py --offline --once "I want a refund for order A100"

# real LLM
python 06-multi-agent-systems/07-swarm-handoffs/main.py
```

Expected (offline, above 3 messages):
```
orders> Done: A200: router, status=shipped ...      [path: triage -> orders]
tech> Done: For router: 1) power-cycle ...           [path: orders -> triage -> tech]
refunds> Done: Refund of INR 2999 issued for A100    [path: tech -> triage -> refunds]
```
`path` mein dikhta hai ki conversation kis agent se kis agent tak gayi, aur `context` mein `order_id` / `refunds` set hote dikhenge.

Fake orders: `A100` (delivered, refundable), `A200` (shipped, refund blocked). Real LLM ke saath "refund A200" try karo. Refunds agent ko tool se "Cannot refund" milega.

## Tests

```bash
pytest 06-multi-agent-systems/07-swarm-handoffs -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_triage_hands_off_to_refunds_and_refund_is_issued` | Handoff + specialist tool + context update |
| `test_context_variables_shared_and_visible_in_prompt` | Context tool ne set kiya aur system prompt mein inject hua |
| `test_tech_path` | Doosra route |
| `test_handoff_not_in_allowed_list_is_rejected` | Allowed-edges guard |
| `test_ping_pong_guard` | A↔B loop → `max_handoffs` |
| `test_conversation_continues_with_active_agent` | Agla message seedha active agent (refunds) ke paas |

## Traces mein kya dekhna hai

```
[swarm:tool] triage -> refunds (refund request)
[swarm:tool] [refunds] issue_refund({'order_id': 'A100', ...}) -> Refund of INR 2999 ...
```
Real LLM pe dhyan do: kya triage khud answer dene lagta hai (instructions todna)? Kya specialists off-topic pe triage ko wapas bhejte hain?

## Tinker karo 🔧

1. **Naya peer**: `billing` agent (tool: `get_invoice(order_id)`) banao, triage ke `handoffs` mein add karo.
2. **Human escalation**: `human` peer banao jiska "LLM" `input()` se jawab de. `max_handoffs` hit hone pe wahan route karo.
3. **Input filter**: handoff ke time sirf last 4 messages naye agent ko do. Kya quality girti hai? Tokens kitne bache?
4. **Mesh vs triage**: har agent ko har doosre agent ka handoff do. Ping-pong kitni baar hota hai?
5. **Supervisor version**: yahi support flow project 03 ke supervisor style mein banao aur LLM calls count compare karo.
6. **Approval gate**: `issue_refund` se pehle human confirmation (agentkit `Agent` ka `approve` hook jaisa) add karo.
