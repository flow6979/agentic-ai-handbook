**Language:** Hinglish · [English](CONCEPTS.en.md)

# 03 · Handoffs (Control transfer between agents)

## Basic idea

Customer care pe call karo: pehle **reception (triage)** uthata hai, sunta hai, phir
bolta hai *"main aapko billing department se connect karta hoon"*. Ab billing wala baat karta
hai, aur usko pata hai ki pehle kya bola gaya tha.

Yahi **handoff** hai: **control** ek agent se dusre ko chala jaata hai.

```
          transfer_to_billing           transfer_to_triage        transfer_to_tech
 ┌────────┐ ─────────────► ┌─────────┐ ─────────────► ┌────────┐ ─────────────► ┌──────┐
 │ triage │                │ billing │                │ triage │                │ tech │
 └────────┘                └─────────┘                └────────┘                └──────┘
      ▲                         │ refund_invoice()                                  │ unlock_account()
      │                         ▼                                                   ▼
   user msg 1              "Refunded INV-2"        user msg 2 ...             "Unlocked"
```

OpenAI Swarm / Agents SDK (`handoffs=[...]`), LangGraph Swarm, aur AutoGen Swarm isi pattern
ko implement karte hain.

## Handoff kaise kaam karta hai (mechanics)

Trick simple hai: **transfer ek tool call hi hai**.

```
 1. Triage ko tools diye: transfer_to_billing, transfer_to_tech
 2. LLM bolta hai:   tool_call: transfer_to_billing(reason="double charge")
 3. Runner (Swarm) dekhta hai: naam "transfer_to_" se shuru hota hai
      → active_agent = billing
 4. Agle LLM call mein:
      system prompt = billing ka
      tools         = billing ke (list_invoices, refund_invoice, transfer_to_triage)
      messages      = SAME shared history (user ka pehla message bhi)
```

```
                     ┌──────────── Swarm.run loop ─────────────┐
 shared messages ───►│ system = ACTIVE agent ka prompt          │
                     │ tools  = ACTIVE agent ke tools + transfers│
                     │ LLM call                                  │
                     │   ├─ normal tool? → chalao, result add    │
                     │   ├─ transfer_to_X? → active = X          │
                     │   └─ no tool call? → final answer, return │
                     └──────────────────────────────────────────┘
```

## Teen cheezein jo transfer hoti hain vs nahi

| Cheez | Transfer hoti hai? |
|---|---|
| Conversation history (messages) | Haan, shared |
| `context` variables (customer_id) | Haan, runner ke paas rehte hain, tools ko inject hote hain |
| System prompt | Nahi, naye agent ka lagta hai |
| Tools | Nahi, naye agent ke milte hain |

### Context variables: LLM se chhupa ke

`refund_invoice(invoice_id, context)` mein `context` ko JSON schema se **hata diya** gaya hai.
LLM sirf `invoice_id` bhejta hai; runner `context={"customer_id": "C-101"}` khud inject karta hai.

**Kyun?** Agar LLM customer_id bhejta, to prompt injection se koi bol sakta tha *"refund
C-999 ka invoice"*. Security-sensitive identifiers hamesha **server-side** se aane chahiye.

## Handback aur multi-turn

- **Handback**: billing ke paas `transfer_to_triage` hai. Galat department mein aaye sawaal wapas jaate hain.
- **Multi-turn**: `SwarmResult.active_agent` agle user message pe `start=` ban jaata hai, taaki
  user billing se hi baat karta rahe jab tak zaroorat ho.

## Subtypes / variations

1. **Router handoff** (yeh project): triage sirf route karta hai
2. **Peer-to-peer / swarm**: koi bhi agent kisi ko bhi transfer kare (fully connected)
3. **Handoff with input filter**: transfer ke waqt history trim/summarize karo (token bachao)
4. **Human handoff**: `transfer_to_human` escalation (ticket banao, live agent ko do)
5. **Structured handoff payload**: `transfer_to_billing(reason, priority)` jisse next agent ko metadata mile

## Handoff vs Agent-as-Tool (project 02)

```
 Agent-as-Tool:  Manager ──call──► Specialist ──result──► Manager ──► User
                 (manager hamesha user se baat karta hai)

 Handoff:        Triage ──transfer──► Billing ──────────────────────► User
                 (ab billing hi user se baat karta hai)
```

## Kab use karein / kab nahi

**Use karo:** alag departments/skills, lambi conversation, har specialist ke alag tools/permissions.

**Mat use karo:** ek hi jawab mein kai specialists ka result combine karna ho (agent-as-tool / supervisor lo).

## Pitfalls

- **Ping-pong**: triage → billing → triage → billing... → `max_handoffs` lagao (yahan 4)
- **History bloat**: lambi shared history har agent ko bhejna mehenga hai → summarization filter
- **Vague instructions**: "kab transfer karna hai" clearly likho, warna LLM khud solve karne lagta hai
- **Tool leakage**: triage ke paas refund tool nahi hona chahiye. Least privilege rakho.

## Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Agent definition (instructions, tools, handoffs) | `handoff_swarm.py` → `SwarmAgent` |
| Transfer tools auto-generate | `SwarmAgent.transfer_tool`, `Swarm._tools_for` |
| Active agent switch, shared history | `Swarm.run` |
| Context injection (hidden from LLM) | `Swarm._call` + `handoff_support.py` schema pop |
| Ping-pong guard | `max_handoffs` in `Swarm.run` |
| Departments + fake DB | `handoff_support.py` → `build_agents()` |
| Multi-turn chat, handback | `main.py` (active agent carry forward) |
