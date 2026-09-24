import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentkit import ScriptedLLM, call, tool_response
from httpsvc_agents import build_orchestrator
from httpsvc_client import AgentClient, RemoteAgentError
from httpsvc_registry import create_registry_app
from httpsvc_service import create_agent_app

TOKEN = "t"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def world(handler=lambda s: s.upper(), poster=None):
    callbacks = []
    apps = {
        "http://registry": create_registry_app(TOKEN),
        "http://upper": create_agent_app("upper", ["shout"], handler, token=TOKEN,
                                         callback_poster=poster or (lambda url, p: callbacks.append((url, p)))),
    }
    clients = {b: TestClient(a, base_url=b) for b, a in apps.items()}
    clients["http://registry"].post("/register", json={"name": "upper", "url": "http://upper", "skills": ["shout"]}, headers=AUTH)
    client = AgentClient("http://registry", TOKEN, http_factory=lambda b: clients[b], sleep=lambda s: None)
    return client, clients, callbacks


def test_discovery_and_sync_invoke():
    client, _, _ = world()
    assert client.discover("shout")[0]["url"] == "http://upper"
    assert client.discover("nope") == []
    assert client.invoke_skill("shout", "hi") == "HI"
    with pytest.raises(LookupError):
        client.invoke_skill("nope", "x")


def test_auth_required():
    _, clients, _ = world()
    assert clients["http://upper"].post("/invoke", json={"input": "x"}).status_code == 401
    bad = AgentClient("http://registry", "wrong", http_factory=lambda b: clients[b])
    with pytest.raises(PermissionError):
        bad.invoke("http://upper", "x")


def test_async_job_poll_and_webhook():
    client, _, callbacks = world()
    job_id = client.submit_job("http://upper", "hello", callback_url="http://me/cb")
    job = client.wait_for_job("http://upper", job_id, poll_every=0)
    assert job == {"id": job_id, "status": "done", "output": "HELLO", "error": None}
    assert callbacks == [("http://me/cb", {"job_id": job_id, "status": "done", "output": "HELLO", "error": None})]


def test_failed_job_reports_error():
    def boom(_):
        raise RuntimeError("llm down")

    client, _, _ = world(handler=boom)
    job = client.wait_for_job("http://upper", client.submit_job("http://upper", "x"), poll_every=0)
    assert job["status"] == "failed" and "llm down" in job["error"]


def test_retry_on_5xx_then_success():
    app, hits = FastAPI(), {"n": 0}

    @app.post("/invoke")
    def flaky():
        hits["n"] += 1
        if hits["n"] < 3:
            from fastapi import HTTPException
            raise HTTPException(503, "busy")
        return {"output": "ok"}

    tc = TestClient(app, base_url="http://flaky")
    client = AgentClient("http://registry", TOKEN, http_factory=lambda b: tc, retries=2, sleep=lambda s: None)
    assert client.invoke("http://flaky", "x") == "ok" and hits["n"] == 3


def test_timeout_gives_up_after_retries():
    attempts = []

    def handler(request):
        attempts.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://slow")
    client = AgentClient("http://registry", TOKEN, http_factory=lambda b: mock, retries=2, sleep=lambda s: None)
    with pytest.raises(RemoteAgentError, match="giving up after 3"):
        client.invoke("http://slow", "x")
    assert len(attempts) == 3


def test_orchestrator_uses_remote_agents_as_tools():
    client, _, _ = world()
    llm = ScriptedLLM([
        tool_response(call("list_remote_skills")),
        tool_response(call("call_remote_agent", skill="shout", text="hey")),
        "Remote said HEY",
    ])
    res = build_orchestrator(llm, client, verbose=False).run("make it loud")
    tool_outputs = [m.content for m in res.messages if m.role == "tool"]
    assert tool_outputs == ['{"upper": ["shout"]}', "HEY"]
