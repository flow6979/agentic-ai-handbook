"""Generic project runner: handbook ke KISI BHI project ka asli `main.py` website se chalao.

    {"lab": "project", "params": {"project": "02-agentic-architectures/01-prompt-chaining",
                                  "args": ["Python async for beginners", "--tone", "friendly"],
                                  "stdin": ""}}

Kya hota hai:
  1. project folder sys.path pe, cwd wahi (data files relative path se milti hain)
  2. env: LLM_MODEL = user ka model, provider key env vars (e.g. GROQ_API_KEY) = user ki key
  3. sys.argv = ["main.py", "--offline"?, *args]; stdin = diya gaya text (REPL demos ke liye)
  4. runpy se main.py `__main__` ki tarah chalta hai; stdout/stderr ki har line UI ko event banke jaati hai
  5. har LLM call count hoti hai (llm_call events), end mein env/cwd/sys.path wapas

Wahi code jo terminal mein `python <project>/main.py` se chalta hai, bina badle.
"""
from __future__ import annotations

import io
import json
import os
import re
import runpy
import sys
import time
from pathlib import Path
from typing import Any

from agentkit.llm.factory import OPENAI_COMPAT

from . import browser_compat
from .registry import Lab
from .runtime import ROOT, LabContext

MANIFEST = Path(__file__).with_name("projects.json")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TRACE = re.compile(r"^\[([\w\-. ]+):(\w+)\]\s?(.*)$")


def manifest() -> dict[str, Any]:
    """projects.json (base: main path, default_args, browser mode) + projects.d/*.json (UI inputs, summary,
    explain cards) merge karke. Section-wise files isliye ki alag log alag section edit kar sakein."""
    base: dict[str, Any] = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    extra_dir = MANIFEST.with_name("projects.d")
    if extra_dir.is_dir():
        for f in sorted(extra_dir.glob("*.json")):
            for pid, extra in json.loads(f.read_text()).items():
                base.setdefault(pid, {"main": f"{pid}/main.py"}).update(extra)
    return base


def build_args(info: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """UI ke form values -> argv, manifest ke `inputs` ke order mein.

    input kinds: text/textarea/choice/number (positional agar `arg` nahi, warna `--flag value`),
                 flag (boolean: sach ho to sirf `--flag`). `prefix` = fixed args pehle (e.g. subcommand).
    """
    args: list[str] = [str(a) for a in info.get("prefix", [])]
    for inp in info.get("inputs", []):
        v = values.get(inp["name"], inp.get("default"))
        if inp.get("kind") == "flag":
            if v in (True, "true", "1", 1):
                args.append(inp["arg"])
            continue
        if v is None or v == "":
            continue
        if inp.get("multi") and isinstance(v, str):  # e.g. numbers: "4 9 10 13" -> 4 alag args
            vals = v.split()
        else:
            vals = [str(v)]
        if inp.get("arg"):
            args.append(inp["arg"])
        args.extend(vals)
    return args


class _LineStream(io.TextIOBase):
    """stdout/stderr ki har poori line ko UI event banao (tracer lines ko 'step' ki tarah parse karke)."""

    def __init__(self, ctx: LabContext, stream: str, sink: list[str]):
        self.ctx, self.stream, self.sink, self.buf = ctx, stream, sink, ""

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._emit(line)
        return len(s)

    def flush(self) -> None:
        if self.buf:
            self._emit(self.buf)
            self.buf = ""

    def _emit(self, line: str) -> None:
        clean = _ANSI.sub("", line)
        self.sink.append(clean)
        m = _TRACE.match(clean)
        if m:
            self.ctx.emit({"type": "step", "kind": m.group(2), "agent": m.group(1), "text": m.group(3), "stream": self.stream})
        else:
            self.ctx.emit({"type": "output", "stream": self.stream, "text": clean})


def _env_for(ctx: LabContext) -> dict[str, str]:
    env = {"AGENT_VERBOSE": "1"}
    if ctx.offline:
        return env
    if ctx.llm_spec:
        env["LLM_MODEL"] = ctx.llm_spec
    if ctx.embed_spec:
        env["EMBED_MODEL"] = ctx.embed_spec
    for provider, key in ctx.api_keys.items():
        if provider == "anthropic":
            env["ANTHROPIC_API_KEY"] = key
        elif provider == "tavily":
            env["TAVILY_API_KEY"] = key
        elif provider in OPENAI_COMPAT and OPENAI_COMPAT[provider][1]:
            env[OPENAI_COMPAT[provider][1]] = key
    return env


def _meter(ctx: LabContext):
    """Leaf LLM classes ki chat() ko wrap karo taaki har call UI tak jaaye. Returns restore fn + stats."""
    from agentkit.llm.anthropic import AnthropicLLM
    from agentkit.llm.openai_compat import OpenAICompatLLM
    from agentkit.llm.scripted import ScriptedLLM

    stats = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0}
    originals = {}
    for cls in (ScriptedLLM, OpenAICompatLLM, AnthropicLLM):
        orig = cls.chat
        originals[cls] = orig

        def wrapped(self, messages, tools=None, _orig=orig, **kw):
            t0 = time.perf_counter()
            resp = _orig(self, messages, tools, **kw)
            stats["llm_calls"] += 1
            stats["input_tokens"] += resp.usage.input_tokens
            stats["output_tokens"] += resp.usage.output_tokens
            ctx.emit({"type": "llm_call", "n": stats["llm_calls"], "model": resp.model or self.model,
                      "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
                      "ms": round((time.perf_counter() - t0) * 1000), "tool_calls": len(resp.tool_calls)})
            return resp

        cls.chat = wrapped  # type: ignore[method-assign]

    def restore():
        for cls, orig in originals.items():
            cls.chat = orig  # type: ignore[method-assign]

    return restore, stats


REPLAYS = Path(__file__).with_name("data") / "project_replays.json"


def _replay(ctx: LabContext, project: str) -> dict:
    """Browser mein na chalne wale project ka recorded asli run, line by line (UI isse animate karta hai)."""
    recs = json.loads(REPLAYS.read_text()) if REPLAYS.exists() else {}
    rec = recs.get(project)
    if not rec:
        raise ValueError(f"{project} browser mein nahi chal sakta aur iska recording bhi nahi mila")
    ctx.emit({"type": "replay", "recorded_at": rec["recorded_at"], "command": rec["command"], "python": rec["python"]})
    sink: list[str] = []
    streams = {"stdout": _LineStream(ctx, "stdout", sink), "stderr": _LineStream(ctx, "stderr", sink)}
    for line in rec["lines"]:
        streams[line["stream"]]._emit(line["text"])
    return {"project": project, "replay": True, "recorded_at": rec["recorded_at"], "command": rec["command"],
            "exit_code": rec["exit_code"], "lines": len(sink), "output_tail": "\n".join(sink[-40:]), "shims": [],
            "ms": rec["ms"], "llm_calls": 0, "input_tokens": 0, "output_tokens": 0}


def run(ctx: LabContext) -> dict:
    project = str(ctx.params.get("project", "")).strip().strip("/")
    info = manifest().get(project, {})
    if info.get("browser") == "replay":
        return _replay(ctx, project)
    main_rel = info.get("main", f"{project}/main.py")
    main_path = (ROOT / main_rel).resolve()
    if ROOT not in main_path.parents or not main_path.exists():
        raise ValueError(f"unknown project {project!r}")
    proj_dir = main_path.parent

    if isinstance(ctx.params.get("values"), dict):
        args = build_args(info, ctx.params["values"])
    elif ctx.params.get("args"):
        args = [str(a) for a in ctx.params["args"]]
    elif info.get("inputs"):
        args = build_args(info, {})
    else:
        args = [str(a) for a in info.get("default_args") or []]
    argv = ["main.py", *(["--offline"] if ctx.offline and info.get("offline_flag", True) else []), *args]

    browser_compat.apply()
    browser_compat.notes.clear()

    lines: list[str] = []
    old = (sys.argv, sys.stdin, sys.stdout, sys.stderr, os.getcwd(), list(sys.path))
    env = _env_for(ctx)
    old_env = {k: os.environ.get(k) for k in env}
    before_modules = set(sys.modules)
    restore_meter, stats = _meter(ctx)
    out, err = _LineStream(ctx, "stdout", lines), _LineStream(ctx, "stderr", lines)
    t0 = time.perf_counter()
    exit_code = 0
    ctx.emit({"type": "start", "project": project, "argv": argv[1:]})
    try:
        os.environ.update(env)
        sys.argv = argv
        sys.stdin = io.StringIO(str(ctx.params.get("stdin") or info.get("default_stdin") or ""))
        sys.stdout, sys.stderr = out, err  # type: ignore[assignment]
        sys.path.insert(0, str(proj_dir))
        os.chdir(proj_dir)
        with browser_compat.sync_asyncio():
            runpy.run_path(str(main_path), run_name="__main__")
    except EOFError:
        # interactive demo (input() loop) ne diya gaya stdin khatam kar diya = normal exit
        out.write("[stdin khatam: interactive demo yahin ruka]\n")
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if exit_code and e.code is not None and not isinstance(e.code, int):
            err.write(f"{e.code}\n")
    finally:
        out.flush()
        err.flush()
        restore_meter()
        sys.argv, sys.stdin, sys.stdout, sys.stderr = old[0], old[1], old[2], old[3]
        os.chdir(old[4])
        sys.path[:] = old[5]
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # project ke modules hatao taaki agla project apne same-naam modules fresh import kare
        for name in set(sys.modules) - before_modules:
            mod = sys.modules.get(name)
            f = getattr(mod, "__file__", "") or ""
            if f.startswith(str(ROOT)) and "/common/" not in f and "/lab-api/" not in f:
                sys.modules.pop(name, None)

    if exit_code not in (0, None):
        raise RuntimeError(f"main.py exited with code {exit_code}: " + "\n".join(lines[-15:]))
    return {"project": project, "argv": argv[1:], "exit_code": exit_code, "lines": len(lines),
            "output_tail": "\n".join(lines[-40:]), "shims": sorted(browser_compat.notes),
            "ms": round((time.perf_counter() - t0) * 1000), **stats}


LAB = Lab(id="project", project="*", run=run,
          smoke_cases=[{"project": "02-agentic-architectures/01-prompt-chaining"}, {"project": "05-agent-communication/07-mcp/01-mcp-server-stdio"}])
