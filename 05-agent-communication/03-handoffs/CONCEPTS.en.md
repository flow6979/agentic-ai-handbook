**Language:** [Hinglish](CONCEPTS.md) · English

# 03 · Handoffs (control transfer between agents)

## Basic idea

Call customer care: first the **reception (triage)** picks up, listens, and then
says *"let me connect you to the billing department"*. Now the billing person talks
to you, and they know what was said earlier.

That is a **handoff**: **control** moves from one agent to another.

```
          transfer_to_billing           transfer_to_triage        transfer_to_tech
 ┌────────┐ ─────────────► ┌─────────┐ ─────────────► ┌────────┐ ─────────────► ┌──────┐
 │ triage │                │ billing │                │ triage │                │ tech │
 └────────┘                └─────────┘                └────────┘                └──────┘
      ▲                         │ refund_invoice()                                  │ unlock_account()
      │                         ▼                                                   ▼
   user msg 1              "Refunded INV-2"        user msg 2 ...             "Unlocked"
```

OpenAI Swarm / Agents SDK (`handoffs=[...]`), LangGraph Swarm and AutoGen Swarm all implement
this pattern.

## How a handoff works (mechanics)

The trick is simple: **a transfer is just a tool call**.

```
 1. Triage is given tools: transfer_to_billing, transfer_to_tech
 2. The LLM says:    tool_call: transfer_to_billing(reason="double charge")
 3. The runner (Swarm) sees the name starts with "transfer_to_"
      → active_agent = billing
 4. On the next LLM call:
      system prompt = billing's
      tools         = billing's (list_invoices, refund_invoice, transfer_to_triage)
      messages      = the SAME shared history (including the user's first message)
```

```
                     ┌──────────── Swarm.run loop ──────────────┐
 shared messages ───►│ system = the ACTIVE agent's prompt        │
                     │ tools  = ACTIVE agent's tools + transfers │
                     │ LLM call                                  │
                     │   ├─ normal tool? → run it, add result    │
                     │   ├─ transfer_to_X? → active = X          │
                     │   └─ no tool call? → final answer, return │
                     └───────────────────────────────────────────┘
```

## What transfers and what does not

| Thing | Does it transfer? |
|---|---|
| Conversation history (messages) | Yes, shared |
| `context` variables (customer_id) | Yes, they stay with the runner and are injected into tools |
| System prompt | No, the new agent's prompt applies |
| Tools | No, the new agent's tools are used |

### Context variables: hidden from the LLM

In `refund_invoice(invoice_id, context)`, `context` has been **removed** from the JSON schema.
The LLM only sends `invoice_id`; the runner injects `context={"customer_id": "C-101"}` itself.

**Why?** If the LLM sent the customer_id, someone could use prompt injection to say *"refund
C-999's invoice"*. Security-sensitive identifiers must always come from the **server side**.

## Handback and multi-turn

- **Handback**: billing has `transfer_to_triage`. Questions that landed in the wrong department go back.
- **Multi-turn**: `SwarmResult.active_agent` becomes `start=` for the next user message, so the
  user keeps talking to billing for as long as needed.

## Subtypes / variations

1. **Router handoff** (this project): triage only routes
2. **Peer-to-peer / swarm**: any agent can transfer to any other (fully connected)
3. **Handoff with input filter**: trim/summarize the history during the transfer (saves tokens)
4. **Human handoff**: `transfer_to_human` escalation (create a ticket, hand to a live agent)
5. **Structured handoff payload**: `transfer_to_billing(reason, priority)` so the next agent gets metadata

## Handoff vs Agent-as-Tool (project 02)

```
 Agent-as-Tool:  Manager ──call──► Specialist ──result──► Manager ──► User
                 (the manager always talks to the user)

 Handoff:        Triage ──transfer──► Billing ──────────────────────► User
                 (now billing itself talks to the user)
```

## When to use it / when not to

**Use it:** separate departments/skills, long conversations, different tools/permissions per specialist.

**Do not use it:** when one answer must combine results from several specialists (use agent-as-tool / a supervisor).

## Pitfalls

- **Ping-pong**: triage → billing → triage → billing... → set `max_handoffs` (4 here)
- **History bloat**: sending a long shared history to every agent is expensive → a summarization filter
- **Vague instructions**: write clearly "when to transfer", otherwise the LLM starts solving it itself
- **Tool leakage**: triage should not have the refund tool. Keep least privilege.

## How this project uses it

| Concept | Where |
|---|---|
| Agent definition (instructions, tools, handoffs) | `handoff_swarm.py` → `SwarmAgent` |
| Transfer tools auto-generated | `SwarmAgent.transfer_tool`, `Swarm._tools_for` |
| Active agent switch, shared history | `Swarm.run` |
| Context injection (hidden from the LLM) | `Swarm._call` + `handoff_support.py` schema pop |
| Ping-pong guard | `max_handoffs` in `Swarm.run` |
| Departments + fake DB | `handoff_support.py` → `build_agents()` |
| Multi-turn chat, handback | `main.py` (active agent carried forward) |
