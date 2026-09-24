"""Offline fixtures: fake API responses (httpx.MockTransport) + scripted LLM.

`--offline` demo aur tests dono isi ko use karte hain, taaki bina internet/keys ke chale.
"""
from __future__ import annotations

import httpx

from agentkit import ScriptedLLM, call, tool_response

WIKI_SEARCH = {"query": {"search": [
    {"title": "Eiffel Tower", "snippet": "The <span>Eiffel Tower</span> is a wrought-iron lattice tower in Paris"},
    {"title": "Gustave Eiffel", "snippet": "French civil engineer"},
]}}
WIKI_SUMMARY = {
    "title": "Eiffel Tower",
    "extract": "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. "
    "It was completed in 1889 and is 330 metres tall.",
}
GEO = {"results": [{"name": "Paris", "country": "France", "latitude": 48.85, "longitude": 2.35}]}
FORECAST = {
    "current": {"temperature_2m": 18.2, "wind_speed_10m": 9.4, "weather_code": 2},
    "daily": {
        "time": ["2026-09-24", "2026-09-25", "2026-09-26"],
        "temperature_2m_max": [21.0, 19.5, 17.8],
        "temperature_2m_min": [12.1, 11.4, 10.9],
        "precipitation_probability_max": [10, 40, 70],
        "weather_code": [2, 3, 61],
    },
}
FX = {"amount": 500.0, "base": "USD", "date": "2026-09-23", "rates": {"EUR": 427.35}}


def mock_handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "en.wikipedia.org" and path == "/w/api.php":
        return httpx.Response(200, json=WIKI_SEARCH)
    if host == "en.wikipedia.org" and path.startswith("/api/rest_v1/page/summary/"):
        return httpx.Response(200, json=WIKI_SUMMARY)
    if host == "geocoding-api.open-meteo.com":
        name = request.url.params.get("name", "")
        return httpx.Response(200, json=GEO if name.lower() == "paris" else {})
    if host == "api.open-meteo.com":
        return httpx.Response(200, json=FORECAST)
    if host == "api.frankfurter.dev":
        return httpx.Response(200, json=FX)
    return httpx.Response(404, json={"error": f"no fixture for {request.url}"})


def offline_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(mock_handler))


def offline_llm() -> ScriptedLLM:
    """Ek 'nakli' LLM jo wahi karta hai jo ek achha model karta: tools chalao, phir jawab do."""
    return ScriptedLLM([
        tool_response(
            call("get_weather", city="Paris"),
            call("convert_currency", amount=500, from_currency="USD", to_currency="EUR"),
            text="I need weather and currency; both are independent so I'll call them together.",
        ),
        tool_response(call("wikipedia_summary", title="Eiffel Tower")),
        "Paris right now: 18.2°C, partly cloudy. Next days: 21/12°C, 19.5/11.4°C, then rain likely "
        "(70%) on 26-Sep, so pack an umbrella. 500 USD ≈ 427.35 EUR (ECB rate of 2026-09-23). "
        "Fun fact: the Eiffel Tower was completed in 1889 and is 330 m tall. "
        "(Sources: get_weather/open-meteo, convert_currency/frankfurter, wikipedia_summary)",
    ])
