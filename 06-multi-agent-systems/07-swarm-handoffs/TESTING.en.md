**Language:** [Hinglish](TESTING.md) · English

# 07 · Swarm & Handoffs: Test & Tinker

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

Expected (offline, the 3 messages above):
```
orders> Done: A200: router, status=shipped ...      [path: triage -> orders]
tech> Done: For router: 1) power-cycle ...           [path: orders -> triage -> tech]
refunds> Done: Refund of INR 2999 issued for A100    [path: tech -> triage -> refunds]
```
`path` shows which agent the conversation went through, and in `context` you will see `order_id` / `refunds` getting set.

Fake orders: `A100` (delivered, refundable), `A200` (shipped, refund blocked). With a real LLM, try "refund A200". The refunds agent will get "Cannot refund" back from the tool.

## Tests

```bash
pytest 06-multi-agent-systems/07-swarm-handoffs -v
```

| Test | What it proves |
|---|---|
| `test_triage_hands_off_to_refunds_and_refund_is_issued` | Handoff + specialist tool + context update |
| `test_context_variables_shared_and_visible_in_prompt` | The tool set the context and it was injected into the system prompt |
| `test_tech_path` | A second route |
| `test_handoff_not_in_allowed_list_is_rejected` | Allowed-edges guard |
| `test_ping_pong_guard` | A↔B loop → `max_handoffs` |
| `test_conversation_continues_with_active_agent` | The next message goes straight to the active agent (refunds) |

## What to look for in traces

```
[swarm:tool] triage -> refunds (refund request)
[swarm:tool] [refunds] issue_refund({'order_id': 'A100', ...}) -> Refund of INR 2999 ...
```
With a real LLM, watch: does triage start answering by itself (breaking its instructions)? Do specialists send off-topic requests back to triage?

## Tinker 🔧

1. **A new peer**: create a `billing` agent (tool: `get_invoice(order_id)`) and add it to triage's `handoffs`.
2. **Human escalation**: create a `human` peer whose "LLM" answers via `input()`. Route there when `max_handoffs` is hit.
3. **Input filter**: on handoff, give the new agent only the last 4 messages. Does quality drop? How many tokens did you save?
4. **Mesh vs triage**: give every agent a handoff to every other agent. How often does ping-pong happen?
5. **Supervisor version**: build the same support flow in project 03's supervisor style and compare the number of LLM calls.
6. **Approval gate**: add a human confirmation before `issue_refund` (like the `approve` hook on agentkit's `Agent`).
