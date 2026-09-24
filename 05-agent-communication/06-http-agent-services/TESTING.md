# 06 · HTTP Agent Services: Test aur tinker kaise karein

## Offline (koi port nahi, sab in-process TestClient se)

```bash
python 05-agent-communication/06-http-agent-services/main.py --offline
```

Dikhega:
1. **SYNC**: orchestrator ne `list_remote_skills` phir 2 remote calls kiye (stderr pe `[orchestrator:tool]`)
2. **ASYNC JOB**: `submitted <id> -> {'status': 'done', ...}`

## Real: 4 terminals (repo root se, `.env` mein LLM set ho)

```bash
# T1: registry
python 05-agent-communication/06-http-agent-services/main.py serve registry --port 8000
# T2: summarizer (startup pe registry mein register hoga)
python 05-agent-communication/06-http-agent-services/main.py serve summarizer --port 8001
# T3: sentiment
python 05-agent-communication/06-http-agent-services/main.py serve sentiment --port 8002
# T4: client
python 05-agent-communication/06-http-agent-services/main.py ask "Review: fast phone, gorgeous screen, battery dies by noon."
python 05-agent-communication/06-http-agent-services/main.py job summarizer "paste a long paragraph"
```

curl se khud poke karo:

```bash
curl -s localhost:8000/agents | jq                     # registry
curl -s localhost:8001/info
curl -s -X POST localhost:8001/invoke -H 'content-type: application/json' -d '{"input":"hi"}'       # 401
curl -s -X POST localhost:8001/invoke -H 'content-type: application/json' \
     -H 'Authorization: Bearer dev-secret' -d '{"input":"Long text here..."}' | jq
curl -s -X POST localhost:8001/jobs -H 'content-type: application/json' \
     -H 'Authorization: Bearer dev-secret' -d '{"input":"Long text"}'           # {"job_id": ...}
curl -s localhost:8001/jobs/<job_id> -H 'Authorization: Bearer dev-secret'
```

FastAPI ka auto docs bhi dekho: http://localhost:8001/docs

Token badalna ho to har terminal mein `export AGENT_SERVICE_TOKEN=...`.

**Failure dekhna:** T3 (sentiment) band karo aur T4 mein `ask` chalao. Registry abhi bhi sentiment
dikhayegi (koi heartbeat nahi). Client 3 attempts ke baad `RemoteAgentError` dega, aur LLM ko woh
error tool result mein milega.

## Tests

```bash
pytest 05-agent-communication/06-http-agent-services -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_discovery_and_sync_invoke` | skill se discovery, sync call, unknown skill → LookupError |
| `test_auth_required` | bina/galat token → 401, client retry nahi karta (PermissionError) |
| `test_async_job_poll_and_webhook` | 202 → poll → done, webhook payload |
| `test_failed_job_reports_error` | handler crash → `status: failed` + error |
| `test_retry_on_5xx_then_success` | 503, 503, 200 → success after retries |
| `test_timeout_gives_up_after_retries` | timeout pe 3 attempts phir give up |
| `test_orchestrator_uses_remote_agents_as_tools` | LLM agent remote services ko tools ki tarah use karta hai |

## Tinker karo

1. **Heartbeat/TTL:** services har 10s pe `/register` dobara karein; registry 30s purani entries hata de.
   Ab band service discovery se gayab ho jaayegi.
2. **Idempotency-Key:** `/jobs` pe `Idempotency-Key` header support karo: same key = same job_id wapas.
   Client retry pe duplicate job nahi banega.
3. **Load balancing:** summarizer do ports pe chalao (8001, 8003). `invoke_skill` mein `found[0]` ki
   jagah random/round-robin choose karo.
4. **Circuit breaker:** ek service lagatar 3 baar fail ho to 30s tak usko call hi mat karo (fast fail).
5. **Streaming:** `/invoke/stream` endpoint banao jo `StreamingResponse` (SSE) se tokens bheje. A2A mein
   `message/stream` yahi hai.
6. **Webhook receiver:** T4 mein ek chhota FastAPI `/cb` endpoint chalao aur `job` command mein
   `callback_url=http://127.0.0.1:9000/cb` do. Polling ki zaroorat khatam.
