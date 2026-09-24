"""Offline fixtures: fake search index, fake pages, aur ek 'smart' ScriptedLLM jo prompt ka TASK dekh ke jawab deta hai."""
from __future__ import annotations

import json

from agentkit import LLMResponse, ScriptedLLM

PAGES = {
    "https://energy.example/solar-cost": "Utility-scale solar electricity cost fell about 90% between 2010 and 2020. "
    "Module prices dropped due to manufacturing scale in China.",
    "https://energy.example/solar-growth": "Solar was the fastest-growing power source in 2023, adding over 400 GW globally.",
    "https://grid.example/storage": "Battery storage helps solar by shifting daytime generation into the evening peak.",
    "https://grid.example/intermittency": "Intermittency is the main challenge of solar: output drops at night and on cloudy days.",
}

INDEX = {
    "cost": ["https://energy.example/solar-cost"],
    "growth": ["https://energy.example/solar-growth", "https://energy.example/solar-cost"],
    "challenge": ["https://grid.example/intermittency"],
    "storage": ["https://grid.example/storage"],
}


def fake_search(query: str) -> list[dict]:
    urls = [u for key, us in INDEX.items() if key in query.lower() for u in us]
    return [{"title": u.rsplit("/", 1)[-1], "url": u, "snippet": PAGES[u][:80]} for u in dict.fromkeys(urls)]


def fake_read(url: str, question: str) -> str:
    return PAGES[url]


def _responder(messages, tools):
    prompt = messages[-1].content or ""
    if "TASK: plan" in prompt:
        return json.dumps({"sub_questions": ["solar cost trend", "solar growth 2023", "solar challenge"]})
    if "TASK: extract_notes" in prompt:
        page = prompt.split("<page>")[1].split("</page>")[0].strip()
        first = page.split(". ")[0].rstrip(".") + "."
        return json.dumps({"notes": [{"claim": first, "source_url": "https://i-made-this-up.example"}]})
    if "TASK: coverage" in prompt:
        has_storage = "storage" in prompt.lower() or "shifting daytime" in prompt
        return json.dumps({"complete": has_storage, "missing": [] if has_storage else ["solar storage solutions"]})
    if "TASK: write_report" in prompt:
        return ("# Solar power: where it stands\n\nSolar got dramatically cheaper [1] and is growing fastest of all "
                "sources [2]. Its main challenge is intermittency [3], which batteries help address [4].\n\n"
                "## Cost and growth\nCosts fell ~90% in a decade [1]; 2023 added 400+ GW [2].\n\n"
                "## Challenges\nNight/cloud output drops [3]; storage shifts energy to evening peak [4].")
    return LLMResponse(content="(unexpected prompt)")


def offline_llm() -> ScriptedLLM:
    return ScriptedLLM(_responder)
