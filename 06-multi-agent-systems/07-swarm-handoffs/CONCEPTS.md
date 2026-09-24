# 07 · Swarm & Handoffs — Bina boss ke team

## Seedhi baat

Customer care pe call karo: pehle receptionist (triage) sunta hai, phir "main aapko refunds team se connect karta hoon" bolta hai. Refunds wala poori baat (conversation) ke saath call le leta hai. **Koi manager beech mein har step decide nahi karta**. Jo agent abhi active hai, wahi decide karta hai ki khud handle kare ya aage **handoff** kare. OpenAI ka Swarm / Agents SDK "handoffs" yahi hai.

```
 user: "order A100 ka refund chahiye"
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

## Handoff kaam kaise karta hai (mechanics)

Handoff = **ek special tool**. Har agent ke `handoffs=["refunds", ...]` list se auto-generated tools bante hain:

```
transfer_to_refunds(reason: str)   → "HANDOFF -> refunds"
```

Swarm loop:
```
active = "triage"
loop:
   resp = llm[active].chat(system=active ka prompt + CONTEXT, messages=poori conversation, tools=active ke tools)
   if koi tool call nahi       → reply user ko, STOP
   if transfer_to_X            → active = X   (conversation same rehti hai!)
   else normal tool            → run(tool, args + shared context)
```

Teen cheezein agents ke beech travel karti hain:
| Kya | Kaise | Kyun |
|---|---|---|
| **Conversation** (`messages`) | Poori history naye agent ko | User ko dobara batana na pade |
| **Context variables** (`context` dict) | Tools padhte/likhte hain; system prompt mein inject | `customer_id`, `order_id` jaise facts share |
| **Active agent** | `SwarmResult.active_agent` | Agla user message usi agent ke paas jaye |

### Context variables ka trick
`lookup_order(order_id, context)` ko ek hidden `context` param milta hai jo **LLM ko schema mein dikhta nahi**. Tool usme `order_id` likh deta hai, aur baad mein refunds agent ke system prompt mein `CONTEXT: {'order_id': 'A200'}` aa jaata hai. Isse LLM ko IDs yaad nahi rakhne padte. Yeh "dependency injection" wala pattern hai.

## Swarm vs Supervisor (important comparison)

```
SUPERVISOR (03)                          SWARM (07)
      ┌─────┐                            A ───► B
      │ SUP │ ◄── har step pe decide         ▲      │
      └──┬──┘                              │      ▼
    ┌────┼────┐                            D ◄─── C
    A    B    C                       (koi center nahi)
```

| | Supervisor | Swarm |
|---|---|---|
| Control | Centralized | Decentralized |
| Extra LLM calls | Har round +1 (supervisor) | 0, handoff hi tool call hai |
| User se baat | Final answer supervisor/writer se | Jo active hai woh seedha |
| Latency | Zyada | Kam |
| Global view | Supervisor ke paas | Kisi ke paas nahi |
| Risk | Supervisor single point of failure | **Ping-pong** (A→B→A→B), lost context |
| Best for | Research/writing pipelines, complex decomposition | Customer support, routing-heavy conversational flows |

## Guards (production must-haves)
1. **Allowed-edges only**: agent sirf apni `handoffs` list mein transfer kar sakta hai. Galat target → error tool result, crash nahi.
2. **max_handoffs**: ping-pong pakdo → "connecting you to a human" (graceful degradation).
3. **max_steps**: poore loop ka ceiling.
4. **Break after handoff**: handoff ke baad purane agent ke baaki tool calls ignore karo, naya agent fresh decide kare.

## Subtypes
| Subtype | Kya |
|---|---|
| **Triage-first** (yeh project) | Entry agent sirf route karta hai |
| **Fully connected mesh** | Har agent kisi ko bhi transfer kar sake (flexible, ping-pong risk zyada) |
| **Handoff with input filter** | Transfer ke time history trim/summarize karke bhejo (context kam) |
| **Handoff back to human** | Escalation path as a peer |
| **Agents-as-tools** (contrast) | Caller control nahi chhodta, sirf sub-agent ka result leta hai (section 05 dekho) |

## Pitfalls
1. **Ping-pong** → `max_handoffs` + clear responsibilities in instructions.
2. **Specialist off-topic handle kare** → instructions mein "otherwise transfer back to triage".
3. **Context bloat**: poori conversation har agent ko jaati hai. Lambi chats mein summarize karo.
4. **Tool permissions leak**: refunds tool sirf refunds agent ke paas hona chahiye (least privilege).
5. **Hidden state bugs**: context dict mutable hai, isliye tests mein assert karo ki kya set hua.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Peer agent definition | `swarm_handoffs.py` → `SwarmAgent(name, instructions, tools, handoffs)` |
| Auto handoff tools | `SwarmAgent.all_tools()` → `transfer_to_<peer>` |
| Swarm loop / active switch | `Swarm.run()` |
| Context variables injection | `CONTEXT: {context}` in system prompt; `tool.run({**args, "context": context})` |
| Allowed-edges guard | `if target not in agent.handoffs` |
| Ping-pong guard | `max_handoffs` → `stopped_reason="max_handoffs"` |
| Conversation continuity | `main.py`: `history`, `active` next turn mein pass |
| Support team | `build_support_swarm()`, `ORDERS` fake DB |
| Per-agent models | `Swarm.__init__` → `llm_factory(a.name)` |
