**Language:** [Hinglish](CONCEPTS.md) · English

# 07 · Swarm & Handoffs: a team without a boss

## The short version

Call customer care: first the receptionist (triage) listens, then says "let me connect you to the refunds team". The refunds person takes the call along with the whole conversation. **No manager sits in the middle deciding every step**. Whichever agent is active right now decides whether to handle it itself or **hand off** to someone else. This is OpenAI's Swarm / Agents SDK "handoffs".

```
 user: "I want a refund for order A100"
   │
   ▼
┌─────────┐ transfer_to_refunds ┌─────────┐ issue_refund(A100) ┌──────────────┐
│ triage  │────────────────────►│ refunds │───────────────────►│ "Refund done"│
└────┬────┘                     └────┬────┘                    └──────────────┘
     │ transfer_to_orders            │ transfer_to_triage (off-topic)
     ▼                               ▼
┌─────────┐ transfer_to_refunds ┌─────────┐
│ orders  │────────────────────►│  tech   │   ← peer-to-peer graph (allowed edges)
└─────────┘                     └─────────┘
```

## How a handoff works (mechanics)

A handoff = **a special tool**. Tools are auto-generated from each agent's `handoffs=["refunds", ...]` list:

```
transfer_to_refunds(reason: str)   → "HANDOFF -> refunds"
```

The swarm loop:
```
active = "triage"
loop:
   resp = llm[active].chat(system=active's prompt + CONTEXT, messages=the whole conversation, tools=active's tools)
   if no tool call             → reply to the user, STOP
   if transfer_to_X            → active = X   (the conversation stays the same!)
   else normal tool            → run(tool, args + shared context)
```

Three things travel between agents:
| What | How | Why |
|---|---|---|
| **Conversation** (`messages`) | The full history goes to the new agent | The user doesn't have to repeat themselves |
| **Context variables** (`context` dict) | Tools read/write it; it is injected into the system prompt | Share facts like `customer_id`, `order_id` |
| **Active agent** | `SwarmResult.active_agent` | The next user message goes to that same agent |

### The context variables trick
`lookup_order(order_id, context)` gets a hidden `context` param that **the LLM never sees in the schema**. The tool writes `order_id` into it, and later `CONTEXT: {'order_id': 'A200'}` shows up in the refunds agent's system prompt. That way the LLM doesn't have to remember IDs. This is the "dependency injection" pattern.

## Swarm vs Supervisor (an important comparison)

```
SUPERVISOR (03)                          SWARM (07)
      ┌─────┐                            A ───► B
      │ SUP │ ◄── decides every step         ▲      │
      └──┬──┘                              │      ▼
    ┌────┼────┐                            D ◄─── C
    A    B    C                       (no centre)
```

| | Supervisor | Swarm |
|---|---|---|
| Control | Centralized | Decentralized |
| Extra LLM calls | +1 every round (the supervisor) | 0, the handoff itself is a tool call |
| Talking to the user | The final answer comes from the supervisor/writer | Whoever is active talks directly |
| Latency | Higher | Lower |
| Global view | The supervisor has it | Nobody has it |
| Risk | The supervisor is a single point of failure | **Ping-pong** (A→B→A→B), lost context |
| Best for | Research/writing pipelines, complex decomposition | Customer support, routing-heavy conversational flows |

## Guards (production must-haves)
1. **Allowed edges only**: an agent can only transfer to agents in its own `handoffs` list. A wrong target → an error tool result, not a crash.
2. **max_handoffs**: catch ping-pong → "connecting you to a human" (graceful degradation).
3. **max_steps**: a ceiling for the whole loop.
4. **Break after handoff**: after a handoff, ignore the old agent's remaining tool calls and let the new agent decide fresh.

## Subtypes
| Subtype | What |
|---|---|
| **Triage-first** (this project) | The entry agent only routes |
| **Fully connected mesh** | Any agent can transfer to any other (flexible, higher ping-pong risk) |
| **Handoff with input filter** | Trim/summarize the history when transferring (less context) |
| **Handoff back to human** | An escalation path as a peer |
| **Agents-as-tools** (contrast) | The caller never gives up control, it only takes the sub-agent's result (see section 05) |

## Pitfalls
1. **Ping-pong** → `max_handoffs` + clear responsibilities in the instructions.
2. **A specialist handles off-topic requests** → put "otherwise transfer back to triage" in the instructions.
3. **Context bloat**: the whole conversation goes to every agent. Summarize long chats.
4. **Tool permissions leak**: the refunds tool should only belong to the refunds agent (least privilege).
5. **Hidden state bugs**: the context dict is mutable, so assert in tests what got set.

## How this project uses it

| Concept | File / function |
|---|---|
| Peer agent definition | `swarm_handoffs.py` → `SwarmAgent(name, instructions, tools, handoffs)` |
| Auto handoff tools | `SwarmAgent.all_tools()` → `transfer_to_<peer>` |
| Swarm loop / active switch | `Swarm.run()` |
| Context variables injection | `CONTEXT: {context}` in the system prompt; `tool.run({**args, "context": context})` |
| Allowed-edges guard | `if target not in agent.handoffs` |
| Ping-pong guard | `max_handoffs` → `stopped_reason="max_handoffs"` |
| Conversation continuity | `main.py`: `history` and `active` are passed into the next turn |
| Support team | `build_support_swarm()`, the `ORDERS` fake DB |
| Per-agent models | `Swarm.__init__` → `llm_factory(a.name)` |
