**Language:** [Hinglish](TESTING.md) · English

# 06 · HTTP Agent Services: how to test and tinker

## Offline (no ports, everything in-process via TestClient)

```bash
python 05-agent-communication/06-http-agent-services/main.py --offline
```

You will see:
1. **SYNC**: the orchestrator called `list_remote_skills`, then made 2 remote calls (`[orchestrator:tool]` on stderr)
2. **ASYNC JOB**: `submitted <id> -> {'status': 'done', ...}`

## Real: 4 terminals (from the repo root, with the LLM set in `.env`)

```bash
# T1: registry
python 05-agent-communication/06-http-agent-services/main.py serve registry --port 8000
# T2: summarizer (registers itself with the registry on startup)
python 05-agent-communication/06-http-agent-services/main.py serve summarizer --port 8001
# T3: sentiment
python 05-agent-communication/06-http-agent-services/main.py serve sentiment --port 8002
# T4: client
python 05-agent-communication/06-http-agent-services/main.py ask "Review: fast phone, gorgeous screen, battery dies by noon."
python 05-agent-communication/06-http-agent-services/main.py job summarizer "paste a long paragraph"
```

Poke at it yourself with curl:

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

Also check FastAPI's auto docs: http://localhost:8001/docs

To change the token, run `export AGENT_SERVICE_TOKEN=...` in every terminal.

**Watching a failure:** stop T3 (sentiment) and run `ask` in T4. The registry will still list sentiment
(there is no heartbeat). The client raises `RemoteAgentError` after 3 attempts, and the LLM receives that
error as the tool result.

## Tests

```bash
pytest 05-agent-communication/06-http-agent-services -v
```

| Test | What it proves |
|---|---|
| `test_discovery_and_sync_invoke` | discovery by skill, sync call, unknown skill → LookupError |
| `test_auth_required` | missing/wrong token → 401, the client does not retry (PermissionError) |
| `test_async_job_poll_and_webhook` | 202 → poll → done, webhook payload |
| `test_failed_job_reports_error` | handler crash → `status: failed` + error |
| `test_retry_on_5xx_then_success` | 503, 503, 200 → success after retries |
| `test_timeout_gives_up_after_retries` | 3 attempts on timeout, then give up |
| `test_orchestrator_uses_remote_agents_as_tools` | the LLM agent uses remote services as tools |

## Tinker with it

1. **Heartbeat/TTL:** have services call `/register` again every 10s; the registry drops entries older than 30s.
   Now a stopped service disappears from discovery.
2. **Idempotency-Key:** support an `Idempotency-Key` header on `/jobs`: same key = same job_id returned.
   A client retry will not create a duplicate job.
3. **Load balancing:** run the summarizer on two ports (8001, 8003). In `invoke_skill`, instead of `found[0]`,
   pick randomly/round-robin.
4. **Circuit breaker:** if a service fails 3 times in a row, do not call it at all for 30s (fail fast).
5. **Streaming:** build an `/invoke/stream` endpoint that sends tokens via `StreamingResponse` (SSE). In A2A this is
   `message/stream`.
6. **Webhook receiver:** in T4, run a small FastAPI `/cb` endpoint and pass
   `callback_url=http://127.0.0.1:9000/cb` to the `job` command. No more need for polling.
