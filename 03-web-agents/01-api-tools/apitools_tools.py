"""Public, no-key APIs ko agent tools banao.

  wikipedia_search   -> en.wikipedia.org/w/api.php (search)
  wikipedia_summary  -> en.wikipedia.org/api/rest_v1/page/summary/<title>
  get_weather        -> open-meteo geocoding + forecast (2 API calls, 1 tool)
  convert_currency   -> frankfurter (ECB exchange rates)

Tool design ke rules jo yahan follow ho rahe hain:
  1. Tool ka output chhota aur relevant ho (poora API JSON nahi, sirf zaroori fields)
  2. Ek tool = ek user-level kaam (geocode + forecast ek hi tool mein, LLM ko 2 step mat karwao)
  3. Clear docstring = LLM ko pata chale kab use karna hai
  4. Galat input pe helpful message, crash nahi
"""
from __future__ import annotations

import re
from urllib.parse import quote

from agentkit import Tool, tool

from apitools_http import ApiClient, trim

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
GEO_API = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_API = "https://api.open-meteo.com/v1/forecast"
FX_API = "https://api.frankfurter.dev/v1/latest"

# open-meteo WMO weather codes (short version)
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "heavy showers", 95: "thunderstorm",
}


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def make_tools(api: ApiClient) -> list[Tool]:
    """Factory: tools ko ApiClient inject karo (tests mein fake client, prod mein real)."""

    @tool
    def wikipedia_search(query: str, limit: int = 3) -> list:
        """Search Wikipedia and return matching article titles with a short snippet.
        Use this first when you don't know the exact article title."""
        data = api.get_json(
            WIKI_API,
            {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": min(limit, 5)},
        )
        hits = data.get("query", {}).get("search", [])
        return [{"title": h["title"], "snippet": _strip_tags(h.get("snippet", ""))} for h in hits]

    @tool
    def wikipedia_summary(title: str) -> str:
        """Get the introduction/summary of a Wikipedia article by its exact title."""
        data = api.get_json(WIKI_SUMMARY + quote(title.replace(" ", "_")))
        return trim(f"{data.get('title', title)}: {data.get('extract', '(no summary)')}", 1200)

    @tool
    def get_weather(city: str) -> dict | str:
        """Current weather and a 3-day forecast for a city (temperatures in Celsius)."""
        geo = api.get_json(GEO_API, {"name": city, "count": 1, "language": "en", "format": "json"})
        if not geo.get("results"):
            return f"No location found for {city!r}. Try the city's English name."
        loc = geo["results"][0]
        wx = api.get_json(
            WEATHER_API,
            {
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current": "temperature_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "forecast_days": 3,
                "timezone": "auto",
            },
        )
        cur, daily = wx["current"], wx["daily"]
        return {
            "location": f"{loc['name']}, {loc.get('country', '')}".strip(", "),
            "now": {
                "temp_c": cur["temperature_2m"],
                "wind_kmh": cur["wind_speed_10m"],
                "sky": WEATHER_CODES.get(cur["weather_code"], f"code {cur['weather_code']}"),
            },
            "next_days": [
                {
                    "date": daily["time"][i],
                    "min_c": daily["temperature_2m_min"][i],
                    "max_c": daily["temperature_2m_max"][i],
                    "rain_chance_pct": daily["precipitation_probability_max"][i],
                    "sky": WEATHER_CODES.get(daily["weather_code"][i], f"code {daily['weather_code'][i]}"),
                }
                for i in range(len(daily["time"]))
            ],
        }

    @tool
    def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
        """Convert money between currencies using today's ECB rates. Use ISO codes like USD, EUR, INR."""
        src, dst = from_currency.upper(), to_currency.upper()
        data = api.get_json(FX_API, {"amount": amount, "base": src, "symbols": dst})
        if dst not in data.get("rates", {}):
            return {"error": f"Rate for {dst} not available", "available": sorted(data.get("rates", {}))[:10]}
        return {"amount": amount, "from": src, "to": dst, "result": data["rates"][dst], "rate_date": data.get("date")}

    return [wikipedia_search, wikipedia_summary, get_weather, convert_currency]
