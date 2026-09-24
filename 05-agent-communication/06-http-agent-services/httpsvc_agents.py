"""Skills (har service ka 'dimaag') + orchestrator agent jo remote agents ko tools ki tarah use karta hai."""
from __future__ import annotations

from agentkit import LLM, Agent, NullTracer, Tracer, tool

from httpsvc_client import AgentClient

SERVICES = {
    # name: (skills, system prompt)
    "summarizer": (["summarize"], "Summarize the user's text in 2 sentences."),
    "sentiment": (["sentiment"], "Classify sentiment as positive, negative or mixed, then give a one-line reason."),
}


def make_skill(llm: LLM, service: str):
    _, system = SERVICES[service]
    return lambda text: llm.complete(text, system=system).strip()


def build_orchestrator(llm: LLM, client: AgentClient, verbose: bool = True) -> Agent:
    @tool
    def list_remote_skills() -> dict:
        """List available remote agents and their skills (from the registry)."""
        return client.skills()

    @tool
    def call_remote_agent(skill: str, text: str) -> str:
        """Send text to the remote agent that has this skill and return its answer."""
        return client.invoke_skill(skill, text)

    return Agent(
        llm, [list_remote_skills, call_remote_agent],
        "You coordinate remote specialist agents over HTTP. First list skills, then call the right agents, "
        "then combine their answers for the user.",
        name="orchestrator", max_steps=8, tracer=Tracer(name="orchestrator") if verbose else NullTracer(),
    )
