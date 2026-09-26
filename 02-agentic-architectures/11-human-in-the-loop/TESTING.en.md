**Language:** [Hinglish](TESTING.md) · English

# 11-human-in-the-loop: Testing and tinkering

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + a key in `.env`.

## 1. Offline demo (scripted LLM + scripted human)

```bash
python 02-agentic-architectures/11-human-in-the-loop/main.py --offline
```

Look for:
- The read-only tools (`get_service_status`, `read_logs`) ran without stopping.
- A pause on `scale_service(replicas=10)` → the scripted human **edited** it to 4.
- `restart_service` → **approve**.
- `delete_database` → `ESCALATIONS: ESC-1`, the tool never ran.
- Both decisions in the `AUDIT LOG`.

## 2. Real LLM: interactive

```bash
python 02-agentic-architectures/11-human-in-the-loop/main.py "checkout service is slow, investigate and fix it"
```

The terminal will show `[a]pprove / [e]dit / [r]eject`. Try:
- reject with the reason "peak hours, don't restart" → what alternative does the model suggest?
- edit `{"replicas": 4}`.

## 3. Real LLM: async (like a Slack approval)

```bash
python 02-agentic-architectures/11-human-in-the-loop/main.py --async "checkout is slow, fix it"
# the output shows the checkpoint path, and the process exits
cat 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json      # inspect the state: messages, pending
python 02-agentic-architectures/11-human-in-the-loop/main.py --resume 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json --decision approve
```

(Run the async demo only with a real LLM: the scripted LLM of `--offline` would replay from the start in the new process.
Offline, cross-process resume is covered by the test `test_pause_checkpoint_resume_in_new_process`.)

## 4. Offline tests

```bash
pytest 02-agentic-architectures/11-human-in-the-loop -v
```

Covered: safe tools don't pause, pause → checkpoint → resume from a new agent, edit (the history is updated too),
reject (the model gets the reason), forbidden → escalation, unknown tool → approval, bad resume → error.

## 5. Tinker with it

1. **Approval timeout:** add a `paused_at` timestamp to `RunState`; on resume, if more than 1 hour has passed,
   auto-reject with "approval expired".
2. **Reviewer context:** in the approval prompt, also show the model's last `content` (reasoning) and the previous 2 tool results.
3. **Plan approval:** add a HITL gate after the planner in `05-plan-and-execute`.
4. **Slack-like API:** build a `/runs/{id}/approve` endpoint in FastAPI that does `load → resume → save`.
5. **Rate-based policy:** make `scale_service` SAFE when `replicas <= 4`, otherwise NEEDS_APPROVAL (an args-dependent policy).
6. **Ask-user tool:** build an `ask_user(question)` tool that always pauses; the human's answer becomes the tool result.
