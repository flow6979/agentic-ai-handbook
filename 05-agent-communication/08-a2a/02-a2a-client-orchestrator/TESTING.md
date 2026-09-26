**Language:** Hinglish · [English](TESTING.en.md)

# A2A Client + Orchestrator: test aur tinker kaise karein

## Setup
```bash
source .venv/bin/activate && pip install -e ".[all]"
cd 05-agent-communication/08-a2a/02-a2a-client-orchestrator
```

## 1. Sab kuch offline (ek command)
Remote agent in-process chalta hai (FastAPI TestClient), LLMs aur "human" scripted hain:
```bash
python main.py --offline "convert 250 USD"                       # LLM orchestrator + input-required
python main.py --offline --mode router "tips for tokyo"          # bina LLM routing
python main.py --offline --mode stream "convert 10 GBP to JPY"   # live SSE events
python main.py --offline --mode poll "tips for paris"            # non-blocking + tasks/get
```

## 2. Real setup (2 terminals)
Terminal 1 (remote agent):
```bash
cd ../01-a2a-server && python main.py            # ya --offline agar sirf orchestrator pe LLM chahiye
```
Terminal 2 (orchestrator, real LLM):
```bash
python main.py "I have 250 USD, how much is that?"     # agent poochhega kaunsi currency -> tum type karo
python main.py "Give me tips for Goa and convert 100 USD to INR"
python main.py --mode stream "convert 99 EUR to AED"
```
Trace mein dekho: `[orchestrator:tool] list_remote_agents({})` → `send_to_agent(...)` → `ask_user(...)` → `send_to_agent(... task_id=...)`.

Token wala agent:
```bash
# T1: python ../01-a2a-server/main.py --offline --token s3cret
python main.py --token s3cret --mode router "tips for london"
```

## 3. Python REPL se khelna
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
Do in-process agents (Travel + ek Echo agent) ke saath: registry, router, input-required with human,
streaming, polling, poora LLM orchestrator loop (tool order assert hota hai), unknown agent error, auth.

## Tinker karo
1. **Embedding router**: `SkillRouter` ko `agentkit.get_embedder()` + `cosine` se replace karo (skill description embed karo). "forex" jaisa synonym ab match hota hai ya nahi, test karo.
2. **Fallback**: `send_to_agent` mein agent down ho (`httpx.ConnectError`) to registry se doosra agent chuno jiske paas same skill ho.
3. **Parallel delegation**: user ek saath do kaam maange to `ThreadPoolExecutor` se dono agents ko parallel bhejo (03 ka `plan_trip` dekho).
4. **Context memory**: orchestrator ko ek dict do `{agent: context_id}` taaki same user ki agli requests usi conversation (`contextId`) mein jaayein.
5. **Result shaping**: `send_to_agent` poora task JSON lautaye to LLM ka token usage kitna badhta hai? `result.usage` compare karo.
6. **Cancel**: `--mode poll` mein 0.1s baad `client.cancel(t.id)` karo aur dekho state kya hoti hai (race condition bhi observe karo).
