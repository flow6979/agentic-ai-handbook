**Language:** [Hinglish](TESTING.md) · English

# A2A Server: how to test and tinker

## Setup
```bash
source .venv/bin/activate && pip install -e ".[all]"
cd 05-agent-communication/08-a2a/01-a2a-server
```

## 1. Run the server
```bash
python main.py --offline          # fake LLM, no key
python main.py                    # real LLM (LLM_MODEL from .env)
python main.py --live-rates       # real FX rates from frankfurter.app (needs internet)
```

## 2. Speak the protocol with curl (second terminal)
```bash
# Discovery
curl -s http://127.0.0.1:9001/.well-known/agent.json | python -m json.tool

# message/send (blocking)
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"message/send",
  "params":{"message":{"kind":"message","role":"user","messageId":"m1",
            "parts":[{"kind":"text","text":"convert 100 USD to INR"}]}}}' | python -m json.tool
```
Look in the response for: `status.state = completed`, text + data in `artifacts[0].parts`, `history`.

**Multi-turn (input-required):**
```bash
# 1) the amount is there, the target currency is not
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m2","parts":[{"kind":"text","text":"convert 50 EUR"}]}}}'
# -> state "input-required", status.message = "Which currency...?"  -> copy the task id

# 2) reply on the same taskId
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":3,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m3","taskId":"<TASK_ID>","parts":[{"kind":"text","text":"GBP"}]}}}'
```

**Streaming (SSE):**
```bash
curl -N -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":4,"method":"message/stream","params":{"message":{"kind":"message","role":"user","messageId":"m4","parts":[{"kind":"text","text":"convert 1 GBP to JPY"}]}}}'
```
The `data:` lines arrive one by one: task → working → "calling convert_currency(...)" → artifact → completed (final).

**Async + polling:**
```bash
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":5,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m5","parts":[{"kind":"text","text":"tips for paris"}]},"configuration":{"blocking":false}}}'
curl -s -X POST http://127.0.0.1:9001/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":6,"method":"tasks/get","params":{"id":"<TASK_ID>","historyLength":2}}'
```

**Auth:**
```bash
python main.py --offline --token s3cret
# now a POST without the "Authorization: Bearer s3cret" header -> 401; the card will show securitySchemes
```

## 3. From the client/orchestrator (project 02)
```bash
cd ../02-a2a-client-orchestrator && python main.py --mode stream "convert 10 GBP to JPY"
```

## 4. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/08-a2a/01-a2a-server -v
```
The tests send raw JSON-RPC (no client lib), so the assertions are on the wire format itself: the card on both
paths, DataPart, input-required multi-turn, historyLength, cancel rules, SSE events, polling,
error codes, crash → `failed`, bearer auth.

## Tinker with it
1. **New skill**: add a `visa_info(country)` tool + `AgentSkill(id="visa-info", tags=["visa", ...])` in the card. 02's router will start picking it automatically.
2. **FilePart artifact**: turn the conversion history into a CSV and send it as an artifact with `FilePart(file=FileContent(name="fx.csv", mime_type="text/csv", bytes=base64...))`.
3. **Artifact streaming in chunks**: send a long answer as 3 `artifact-update` events (`append=True`, and `last_chunk=True` on the last one). The server's `_apply` already handles append.
4. **Persistent TaskStore**: build `TaskStore` on SQLite (save the task JSON). `tasks/get` should keep working after a server restart.
5. **auth-required state**: in `--live-rates` mode, if there is no API key, return `TaskState.auth_required` and tell the client which credential is needed.
6. **Guardrail**: add a check on the user text in the executor (e.g. longer than 2000 chars → `rejected` state + a reason).
