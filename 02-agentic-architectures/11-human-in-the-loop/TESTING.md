# 11-human-in-the-loop: Testing aur tinkering

## Setup
Repo root se `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.

## 1. Offline demo (scripted LLM + scripted human)

```bash
python 02-agentic-architectures/11-human-in-the-loop/main.py --offline
```

Dekho:
- read-only tools (`get_service_status`, `read_logs`) bina rukke chale.
- `scale_service(replicas=10)` pe pause → scripted human ne **edit** karke 4 kiya.
- `restart_service` → **approve**.
- `delete_database` → `ESCALATIONS: ESC-1`, tool kabhi chala nahi.
- `AUDIT LOG` mein dono decisions.

## 2. Real LLM: interactive

```bash
python 02-agentic-architectures/11-human-in-the-loop/main.py "checkout service is slow, investigate and fix it"
```

Terminal mein `[a]pprove / [e]dit / [r]eject` aayega. Try karo:
- reject with reason "peak hours, don't restart" → model kya alternate suggest karta hai?
- edit `{"replicas": 4}`.

## 3. Real LLM: async (Slack-approval jaisa)

```bash
python 02-agentic-architectures/11-human-in-the-loop/main.py --async "checkout is slow, fix it"
# output mein checkpoint path aayega, process exit
cat 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json      # state dekho: messages, pending
python 02-agentic-architectures/11-human-in-the-loop/main.py --resume 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json --decision approve
```

(Async demo real LLM ke saath hi chalao: `--offline` ka scripted LLM naye process mein shuru se replay karega.
Offline mein cross-process resume `test_pause_checkpoint_resume_in_new_process` test karta hai.)

## 4. Offline tests

```bash
pytest 02-agentic-architectures/11-human-in-the-loop -v
```

Cover: safe tools no pause, pause → checkpoint → naye agent se resume, edit (history bhi update),
reject (model ko reason milta hai), forbidden → escalation, unknown tool → approval, galat resume → error.

## 5. Tinker karo

1. **Approval timeout:** `RunState` mein `paused_at` timestamp daalo; resume pe agar 1 ghante se zyada ho gaya to
   auto-reject karo "approval expired".
2. **Reviewer context:** approval prompt mein model ka last `content` (reasoning) aur pichle 2 tool results bhi dikhao.
3. **Plan approval:** `05-plan-and-execute` ke planner ke baad HITL gate lagao.
4. **Slack-like API:** FastAPI mein `/runs/{id}/approve` endpoint banao jo `load → resume → save` kare.
5. **Rate-based policy:** `scale_service` ko SAFE karo jab `replicas <= 4`, warna NEEDS_APPROVAL (args-dependent policy).
6. **Ask-user tool:** ek `ask_user(question)` tool banao jo hamesha pause kare; human ka answer tool result bane.
