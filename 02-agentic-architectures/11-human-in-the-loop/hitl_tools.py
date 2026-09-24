"""DevOps assistant ke fake tools + risk policy.

Har tool ka ek risk level hai. Policy code mein hai (prompt mein nahi!): model chahe kuch bhi
bole, dangerous tool bina approval ke nahi chalega.
"""
from __future__ import annotations

from enum import Enum

from agentkit import tool

SERVICES = {"checkout": {"status": "degraded", "p95_ms": 2400, "replicas": 2},
            "search": {"status": "healthy", "p95_ms": 180, "replicas": 3}}


class Risk(str, Enum):
    SAFE = "safe"                      # read-only: auto-run
    NEEDS_APPROVAL = "needs_approval"  # state change: human approve/edit/reject
    FORBIDDEN = "forbidden"            # agent kabhi nahi chalayega: escalate to on-call


@tool
def get_service_status(service: str) -> dict:
    """Get health status, p95 latency and replica count of a service."""
    if service not in SERVICES:
        raise KeyError(f"unknown service {service!r}")
    return SERVICES[service]


@tool
def read_logs(service: str, lines: int = 5) -> str:
    """Read the last N log lines of a service."""
    if service == "checkout":
        return "\n".join(["WARN db pool exhausted (50/50)", "WARN request queue 830", "ERROR timeout calling payments"][:lines])
    return "INFO all good"


@tool
def restart_service(service: str) -> str:
    """Restart a service (causes ~30s of downtime)."""
    SERVICES[service]["status"] = "healthy"
    SERVICES[service]["p95_ms"] = 300
    return f"{service} restarted, now healthy"


@tool
def scale_service(service: str, replicas: int) -> str:
    """Change the replica count of a service."""
    SERVICES[service]["replicas"] = replicas
    return f"{service} scaled to {replicas} replicas"


@tool
def delete_database(database: str) -> str:
    """Delete a database permanently."""
    raise RuntimeError("this should never run from the agent")


TOOLS = [get_service_status, read_logs, restart_service, scale_service, delete_database]

POLICY: dict[str, Risk] = {
    "get_service_status": Risk.SAFE,
    "read_logs": Risk.SAFE,
    "restart_service": Risk.NEEDS_APPROVAL,
    "scale_service": Risk.NEEDS_APPROVAL,
    "delete_database": Risk.FORBIDDEN,
}
