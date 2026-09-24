import httpx
import pytest

from agentkit import Agent, NullTracer
from apitools_fixtures import mock_handler, offline_client, offline_llm
from apitools_http import ApiClient, ApiError, TTLCache, trim
from apitools_tools import make_tools


def tools_by_name(api):
    return {t.name: t for t in make_tools(api)}


def test_weather_tool_combines_geocode_and_forecast():
    t = tools_by_name(ApiClient(client=offline_client()))["get_weather"]
    out = t.fn(city="Paris")
    assert out["location"] == "Paris, France"
    assert out["now"]["sky"] == "partly cloudy"
    assert len(out["next_days"]) == 3 and out["next_days"][2]["rain_chance_pct"] == 70


def test_unknown_city_is_a_helpful_message_not_a_crash():
    t = tools_by_name(ApiClient(client=offline_client()))["get_weather"]
    assert "No location found" in t.fn(city="Atlantis")


def test_wikipedia_search_strips_html():
    t = tools_by_name(ApiClient(client=offline_client()))["wikipedia_search"]
    assert "<span>" not in t.fn(query="eiffel")[0]["snippet"]


def test_currency_tool():
    t = tools_by_name(ApiClient(client=offline_client()))["convert_currency"]
    assert t.fn(amount=500, from_currency="usd", to_currency="eur")["result"] == 427.35


def test_retry_on_503_then_success():
    hits = {"n": 0}

    def flaky(request):
        hits["n"] += 1
        return httpx.Response(503) if hits["n"] < 3 else mock_handler(request)

    api = ApiClient(client=httpx.Client(transport=httpx.MockTransport(flaky)), sleep=lambda s: None)
    assert api.get_json("https://api.open-meteo.com/v1/forecast")["current"]
    assert api.stats["retries"] == 2


def test_timeout_exhausts_retries_and_raises():
    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    api = ApiClient(client=httpx.Client(transport=httpx.MockTransport(timeout)), retries=1, sleep=lambda s: None)
    with pytest.raises(ApiError, match="network error"):
        api.get_json("https://example.com")


def test_404_is_not_retried():
    api = ApiClient(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))), sleep=lambda s: None)
    with pytest.raises(ApiError, match="404"):
        api.get_json("https://example.com")
    assert api.stats["requests"] == 1


def test_cache_avoids_second_request_and_expires():
    now = {"t": 0.0}
    api = ApiClient(client=offline_client(), cache=TTLCache(ttl=60, clock=lambda: now["t"]))
    api.get_json("https://api.frankfurter.dev/v1/latest", {"base": "USD"})
    api.get_json("https://api.frankfurter.dev/v1/latest", {"base": "USD"})
    assert api.stats == {"requests": 1, "cache_hits": 1, "retries": 0}
    now["t"] = 61
    api.get_json("https://api.frankfurter.dev/v1/latest", {"base": "USD"})
    assert api.stats["requests"] == 2


def test_trim():
    assert trim("a  b\n c") == "a b c"
    assert "trimmed" in trim("word " * 1000, 50)


def test_agent_end_to_end_offline():
    api = ApiClient(client=offline_client())
    res = Agent(offline_llm(), make_tools(api), tracer=NullTracer()).run("Paris trip?")
    tool_results = [m.content for m in res.messages if m.role == "tool"]
    assert len(tool_results) == 3 and not any(r.startswith("ERROR") for r in tool_results)
    assert "427.35" in res.output


def test_tool_error_reaches_llm_as_text():
    api = ApiClient(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
                    retries=0, sleep=lambda s: None)
    from agentkit import ScriptedLLM, call, tool_response

    llm = ScriptedLLM([tool_response(call("get_weather", city="Paris")), "Weather service is down."])
    res = Agent(llm, make_tools(api), tracer=NullTracer()).run("weather?")
    assert [m.content for m in res.messages if m.role == "tool"][0].startswith("ERROR: ApiError")
