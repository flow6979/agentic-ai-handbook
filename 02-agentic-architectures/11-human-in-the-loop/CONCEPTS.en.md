**Language:** [Hinglish](CONCEPTS.md) · English

# Human-in-the-Loop (HITL)

## 1. Why is it needed?

Agents make mistakes: restarting the wrong service, sending the wrong email, issuing the wrong refund. Some actions are **reversible**
(reading logs), some are **irreversible** (deleting a database, transferring money). The rule in production agents:

> **The bigger the blast radius, the more human control.**

And most importantly: **this control must live in code/policy, not in the prompt.** Writing "Please ask before
deleting" in the prompt is not a guardrail; the model can ignore it (or it can be bypassed through prompt
injection).

## 2. Risk tiers (policy)

```
  A tool call arrives
        │
        ▼
  POLICY[tool] ?
   ┌────┼──────────────────┬──────────────────────┐
   │ SAFE                  │ NEEDS_APPROVAL       │ FORBIDDEN
   ▼                       ▼                      ▼
 run immediately      STOP → human:          never run it
 (read_logs)          approve / edit /       → escalation ticket (ESC-1)
                      reject                 → tell the model "BLOCKED"
                      (restart, scale)       (delete_database)

  Unknown tool? → NEEDS_APPROVAL (default-deny: a new tool must not auto-run without review)
```

## 3. Interrupt / Resume (the most important production concept)

Real approvals don't arrive instantly: a button in Slack, a manager's inbox, the next morning. The process can't
wait that long (deploys, crashes, timeouts). So:

```
 Process 1                          Storage                    Process 2 (later)
 ─────────                          ───────                    ─────────────────
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
                                                                 run the tool, the LLM continues...
```

What the state must contain so that it can be resumed from **any process**:
- the full `messages` history (the model's context)
- the `pending` tool calls (requested by the model, not yet run)
- status, step count, audit log, escalations

LangGraph calls this "checkpointer + interrupt"; Temporal/durable execution is the same idea.

## 4. Three human decisions

| Decision | What happens | What the model sees |
|---|---|---|
| **approve** | the tool runs as-is | a normal tool result |
| **edit** | the human changes the args (10 → 4 replicas), then it runs | the tool result; the args are also updated in the history (consistency) |
| **reject** | the tool does not run | `REJECTED by human: <reason>`: the model changes its plan |

**Why edit matters:** "reject + the model tries again" is slow and frustrating. The human just gives the correct value directly.

## 5. Escalation

Some things the agent must **never** do (policy FORBIDDEN). Even then we don't crash: create a ticket
(`ESC-1`), tell the model it's blocked, and let the model inform the user. In real life: PagerDuty/Jira/Slack.

## 6. More HITL patterns (subtypes)

- **Approval gate** (this project): before a risky action.
- **Plan approval:** show the whole plan first (see `05-plan-and-execute`), then execute autonomously.
- **Output review:** human review before sending the final answer/email.
- **Clarification / ask-user tool:** the agent itself asks "which city?" (ambiguous input).
- **Confidence-based escalation:** the model's confidence is low → human queue.
- **Human feedback for learning:** use reject reasons in future prompts/evals.
- **Timeouts:** no approval within X hours → auto-reject or escalate.

## 7. Production pitfalls

- **Approval fatigue:** ask for approval on everything and people will click "approve" without reading. Only ask for risky actions.
- **Context for the reviewer:** showing just `restart_service(checkout)` is not enough. Why? Show the model's reasoning and logs too.
- **Audit log:** who approved/edited what, and when: essential for compliance (`state.audit`).
- **Idempotency:** on resume the tool must not run twice (pop it from pending before executing).
- **Security:** the checkpoint file contains the whole conversation (PII!). Encrypt it / use secure storage.

## 8. How this project uses it

| Concept | File / function |
|---|---|
| Risk tiers + policy (in code) | `hitl_tools.py` → `Risk`, `POLICY` |
| Default-deny for unknown tools | `HITLAgent._drain_pending()` (`policy.get(..., NEEDS_APPROVAL)`) |
| Interrupt (pause) | `_drain_pending()` → `status="waiting_approval"` |
| Checkpoint save/load (JSON) | `RunState.to_json/from_json`, `HITLAgent.save/load` |
| Resume with decision | `HITLAgent.resume()` + `Decision` |
| Edit args (history consistency) | `HITLAgent._edit_call()` |
| Escalation tickets | `_drain_pending()` FORBIDDEN branch, `state.escalations` |
| Audit log | `state.audit` (appended on resume) |
| Interactive vs async (Slack-style) flow | `main.py` (`ask_human`, `--async`, `--resume`) |
