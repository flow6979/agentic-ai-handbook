# A2A Server: test aur tinker kaise karein

## Setup
```bash
source .venv/bin/activate && pip install -e ".[all]"
cd 05-agent-communication/08-a2a/01-a2a-server
```

## 1. Server chalao
```bash
python main.py --offline          # fake LLM, no key
python main.py                    # real LLM (.env ka LLM_MODEL)
python main.py --live-rates       # frankfurter.app se asli FX rates (internet chahiye)
```

## 2. curl se protocol bolo (doosra terminal)
```bash
# Discovery
curl -s http://127.0.0.1:9001/.well-known/agent.json | python -m json.tool

# message/send (blocking)
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"message/send",
  "params":{"message":{"kind":"message","role":"user","messageId":"m1",
            "parts":[{"kind":"text","text":"convert 100 USD to INR"}]}}}' | python -m json.tool
```
Response mein dekho: `status.state = completed`, `artifacts[0].parts` mein text + data, `history`.

**Multi-turn (input-required):**
```bash
# 1) amount hai, target currency nahi
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m2","parts":[{"kind":"text","text":"convert 50 EUR"}]}}}'
# -> state "input-required", status.message = "Which currency...?"  -> task id copy karo

# 2) same taskId pe jawab
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":3,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m3","taskId":"<TASK_ID>","parts":[{"kind":"text","text":"GBP"}]}}}'
```

**Streaming (SSE):**
```bash
curl -N -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":4,"method":"message/stream","params":{"message":{"kind":"message","role":"user","messageId":"m4","parts":[{"kind":"text","text":"convert 1 GBP to JPY"}]}}}'
```
`data:` lines ek-ek karke aati hain: task → working → "calling convert_currency(...)" → artifact → completed (final).

**Async + polling:**
```bash
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":5,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m5","parts":[{"kind":"text","text":"tips for paris"}]},"configuration":{"blocking":false}}}'
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":6,"method":"tasks/get","params":{"id":"<TASK_ID>","historyLength":2}}'
```

**Auth:**
```bash
python main.py --offline --token s3cret
# ab bina "Authorization: Bearer s3cret" header ke POST -> 401; card mein securitySchemes dikhega
```

## 3. Client/orchestrator se (02 project)
```bash
cd ../02-a2a-client-orchestrator && python main.py --mode stream "convert 10 GBP to JPY"
```

## 4. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/08-a2a/01-a2a-server -v
```
Tests raw JSON-RPC bhejte hain (koi client lib nahi), taaki wire format pe hi assert ho: card dono
paths pe, DataPart, input-required multi-turn, historyLength, cancel rules, SSE events, polling,
error codes, crash → `failed`, bearer auth.

## Tinker karo
1. **Naya skill**: `visa_info(country)` tool + card mein `AgentSkill(id="visa-info", tags=["visa", ...])` jodo. 02 ka router use apne aap chunne lagega.
2. **FilePart artifact**: conversion history ko CSV bana ke `FilePart(file=FileContent(name="fx.csv", mime_type="text/csv", bytes=base64...))` artifact mein bhejo.
3. **Artifact streaming in chunks**: lambe jawab ko 3 `artifact-update` events mein bhejo (`append=True`, aakhri mein `last_chunk=True`). Server ka `_apply` already append handle karta hai.
4. **Persistent TaskStore**: `TaskStore` ko SQLite pe banao (task JSON save karo). Server restart ke baad bhi `tasks/get` kaam kare.
5. **auth-required state**: `--live-rates` mode mein agar API key na ho to `TaskState.auth_required` lautao, aur client ko batao kaunsa credential chahiye.
6. **Guardrail**: executor mein user text pe ek check lagao (e.g. 2000 chars se lamba ho to `rejected` state + reason).
