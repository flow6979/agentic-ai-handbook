**Language:** [Hinglish](TESTING.md) · English

# A2A Client + Orchestrator: how to test and tinker

## Setup
```bash
source .venv/bin/activate && pip install -e ".[all]"
cd 05-agent-communication/08-a2a/02-a2a-client-orchestrator
```

## 1. Everything offline (one command)
The remote agent runs in-process (FastAPI TestClient), and the LLMs and the "human" are scripted:
```bash
python main.py --offline "convert 250 USD"                       # LLM orchestrator + input-required
python main.py --offline --mode router "tips for tokyo"          # routing without an LLM
python main.py --offline --mode stream "convert 10 GBP to JPY"   # live SSE events
python main.py --offline --mode poll "tips for paris"            # non-blocking + tasks/get
```

## 2. Real setup (2 terminals)
Terminal 1 (remote agent):
```bash
cd ../01-a2a-server && python main.py            # or --offline if you want the LLM only on the orchestrator
```
Terminal 2 (orchestrator, real LLM):
```bash
python main.py "I have 250 USD, how much is that?"     # the agent will ask which currency -> you type it
python main.py "Give me tips for Goa and convert 100 USD to INR"
python main.py --mode stream "convert 99 EUR to AED"
```
Look in the trace for: `[orchestrator:tool] list_remote_agents({})` → `send_to_agent(...)` → `ask_user(...)` → `send_to_agent(... task_id=...)`.

An agent with a token:
```bash
# T1: python ../01-a2a-server/main.py --offline --token s3cret
python main.py --token s3cret --mode router "tips for london"
```

## 3. Playing from a Python REPL
```python
import sys; sys.path.insert(0, "../01-a2a-server")
from a2a_client import A2AClient, task_answer
c = A2AClient("http://127.0.0.1:9001")
c.card.skills
t = c.send("convert 5 USD"); t.status.state, t.status.message.text()
t = c.send("EUR", task_id=t.id); task_answer(t)
for ev in c.stream("tips for dubai"): print(ev.kind)
```

## 4. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/08-a2a/02-a2a-client-orchestrator -v
```
With two in-process agents (Travel + an Echo agent): registry, router, input-required with a human,
streaming, polling, the full LLM orchestrator loop (the tool order is asserted), unknown agent error, auth.

## Tinker with it
1. **Embedding router**: replace `SkillRouter` with `agentkit.get_embedder()` + `cosine` (embed the skill descriptions). Test whether a synonym like "forex" matches now.
2. **Fallback**: in `send_to_agent`, if the agent is down (`httpx.ConnectError`), pick another agent from the registry that has the same skill.
3. **Parallel delegation**: when the user asks for two things at once, send both agents their work in parallel with a `ThreadPoolExecutor` (see `plan_trip` in 03).
4. **Context memory**: give the orchestrator a dict `{agent: context_id}` so the same user's next requests go into the same conversation (`contextId`).
5. **Result shaping**: if `send_to_agent` returned the whole task JSON, how much would the LLM's token usage grow? Compare `result.usage`.
6. **Cancel**: in `--mode poll`, call `client.cancel(t.id)` after 0.1s and see what state you end up in (observe the race condition too).
