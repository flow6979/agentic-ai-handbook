# Human-in-the-Loop (HITL)

## 1. Kyun zaroori hai?

Agent galti karega: galat service restart, galat email bhejna, galat refund. Kuch actions **reversible**
hain (logs padhna), kuch **irreversible** (database delete, paisa transfer). Production agents mein rule:

> **Jitna bada blast radius, utna zyada human control.**

Aur sabse important: **yeh control code/policy mein hona chahiye, prompt mein nahi.** "Please ask before
deleting" prompt mein likhna guardrail nahi hai; model ise ignore kar sakta hai (ya prompt injection se
bypass ho sakta hai).

## 2. Risk tiers (policy)

```
  Tool call aaya
        │
        ▼
  POLICY[tool] ?
   ┌────┼──────────────────┬──────────────────────┐
   │ SAFE                  │ NEEDS_APPROVAL       │ FORBIDDEN
   ▼                       ▼                      ▼
 turant chalao        RUKO → human:          kabhi mat chalao
 (read_logs)          approve / edit /       → escalation ticket (ESC-1)
                      reject                 → model ko "BLOCKED" batao
                      (restart, scale)       (delete_database)

  Unknown tool? → NEEDS_APPROVAL (default-deny: naya tool bina review ke auto-run na ho)
```

## 3. Interrupt / Resume (sabse important production concept)

Real approvals turant nahi aate: Slack pe button, manager ki inbox, next morning. Process itni der wait
nahi kar sakta (deploy, crash, timeout). Isliye:

```
 Process 1                          Storage                    Process 2 (baad mein)
 ─────────                          ───────                    ─────────────────────
 agent.start(task)
   LLM → scale_service(10)
   policy: NEEDS_APPROVAL
   status = waiting_approval
   save(state) ──────────────►  .hitl_runs/ab12.json
   exit                          { messages, pending,
                                   status, audit, ... }
                                                        ◄────── load(ab12.json)
                                                                 resume(state, Decision(edit,
                                                                         {"replicas": 4}))
                                                                 tool chalao, LLM continue...
```

State mein kya hona chahiye taaki **kisi bhi process** se resume ho sake:
- poori `messages` history (model ka context)
- `pending` tool calls (jo model ne maange, abhi chale nahi)
- status, step count, audit log, escalations

LangGraph isse "checkpointer + interrupt" kehta hai; Temporal/durable execution bhi yahi idea hai.

## 4. Teen human decisions

| Decision | Kya hota hai | Model ko kya dikhta hai |
|---|---|---|
| **approve** | tool as-is chalta hai | normal tool result |
| **edit** | human args badalta hai (10 → 4 replicas), phir chalta hai | tool result; history mein bhi args update (consistency) |
| **reject** | tool nahi chalta | `REJECTED by human: <reason>`: model plan badalta hai |

**Edit kyun important hai:** "reject + model dobara try kare" slow aur frustrating hai. Human seedha sahi value de de.

## 5. Escalation

Kuch cheezein agent ko **kabhi** nahi karni (policy FORBIDDEN). Tab bhi crash nahi karte: ticket banao
(`ESC-1`), model ko batao ki blocked hai, aur model user ko inform kare. Real mein: PagerDuty/Jira/Slack.

## 6. HITL ke aur patterns (subtypes)

- **Approval gate** (yeh project): risky action se pehle.
- **Plan approval:** poora plan pehle dikhao (dekho `05-plan-and-execute`), phir autonomous execute.
- **Output review:** final answer/email bhejne se pehle human review.
- **Clarification / ask-user tool:** agent khud poochhe "kaunsi city?" (ambiguous input).
- **Confidence-based escalation:** model ka confidence kam ho → human queue.
- **Human feedback for learning:** reject reasons ko future prompts/evals mein use karo.
- **Timeouts:** approval X ghante mein na aaye → auto-reject ya escalate.

## 7. Production pitfalls

- **Approval fatigue:** har cheez pe approval maangoge to log bina padhe "approve" karenge. Sirf risky pe maango.
- **Context for reviewer:** sirf `restart_service(checkout)` dikhana kaafi nahi. Kyun? (model ka reasoning, logs) bhi dikhao.
- **Audit log:** kisne, kab, kya approve/edit kiya: compliance ke liye zaroori (`state.audit`).
- **Idempotency:** resume ke time tool do baar na chale (pending se pop karke hi execute).
- **Security:** checkpoint file mein poori conversation hai (PII!). Encrypt/secure storage.

## 8. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Risk tiers + policy (code mein) | `hitl_tools.py` → `Risk`, `POLICY` |
| Default-deny for unknown tools | `HITLAgent._drain_pending()` (`policy.get(..., NEEDS_APPROVAL)`) |
| Interrupt (pause) | `_drain_pending()` → `status="waiting_approval"` |
| Checkpoint save/load (JSON) | `RunState.to_json/from_json`, `HITLAgent.save/load` |
| Resume with decision | `HITLAgent.resume()` + `Decision` |
| Edit args (history consistency) | `HITLAgent._edit_call()` |
| Escalation tickets | `_drain_pending()` FORBIDDEN branch, `state.escalations` |
| Audit log | `state.audit` (resume mein append) |
| Interactive vs async (Slack-style) flow | `main.py` (`ask_human`, `--async`, `--resume`) |
