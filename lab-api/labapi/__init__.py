"""labapi: handbook projects ko website (agent-lab) se chalane ki API.

    from labapi import run, catalog
    run({"lab": "react", "params": {"mode": "native"}, "offline": True}, emit=print)
"""
from .registry import Lab, catalog, labs, run
from .runtime import LabContext, MeteredLLM, use_project

__all__ = ["Lab", "catalog", "labs", "run", "LabContext", "MeteredLLM", "use_project"]
