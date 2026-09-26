"""Browser (Pyodide) compatibility shims, sirf `sys.platform == "emscripten"` pe lagte hain.

Handbook ke projects normal CPython ke liye likhe hain. Browser mein kuch cheezein nahi hoti:

  threads      -> ThreadPoolExecutor / Thread.start ko synchronous bana dete hain (kaam sequentially hota hai)
  sockets      -> httpx ka default transport = synchronous XMLHttpRequest (CORS wale hosts hi chalenge)
  subprocess   -> `python -c <code>` / `python file.py` ko isolated namespace mein exec karte hain

Yeh sirf website ke liye hai; CLI / tests pe koi asar nahi. UI har project pe batata hai ki
kaunsa shim laga (e.g. "parallel kaam yahan sequential chala").
"""
from __future__ import annotations

import contextlib
import io
import sys
from typing import Any

IN_BROWSER = sys.platform == "emscripten"
_applied = False
notes: set[str] = set()  # is run mein kaunse shims kaam aaye (UI ko dikhane ke liye)


def apply() -> None:
    global _applied
    if _applied or not IN_BROWSER:
        return
    _applied = True
    _patch_threads()
    _patch_subprocess()
    _patch_httpx()


# --- asyncio -------------------------------------------------------------------------------
# Pyodide ka asyncio.run() browser ke "stack switching" (JSPI) pe depend karta hai jo har jagah
# nahi hota. Handbook ke async demos sirf coroutines/sleep/queues/gather use karte hain (koi socket
# nahi), isliye ek chhota pure-Python loop kaafi hai: selector ki jagah "bas sleep karo".
@contextlib.contextmanager
def sync_asyncio():
    import asyncio
    import time

    if not IN_BROWSER:
        yield
        return

    class _NoIOSelector:
        def select(self, timeout=None):
            if timeout and timeout > 0:
                time.sleep(min(timeout, 0.5))
            return []

        def close(self):
            pass

        def get_map(self):
            return {}

    class SyncLoop(asyncio.BaseEventLoop):
        def __init__(self):
            super().__init__()
            self._selector = _NoIOSelector()

        def _process_events(self, event_list):
            pass

        def _write_to_self(self):
            pass

    class Policy(asyncio.DefaultEventLoopPolicy):
        def new_event_loop(self):
            notes.add("asyncio")
            return SyncLoop()

    def run(main, *, debug=None, loop_factory=None):
        loop = SyncLoop()
        notes.add("asyncio")
        try:
            return loop.run_until_complete(main)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    import asyncio.runners as runners

    old_policy = asyncio.get_event_loop_policy()
    old_run, old_runners_run = asyncio.run, runners.run
    # Pyodide ka WebLoop "running" maana jaata hai; hamare loop ke liye use thodi der hata do
    prev_running = asyncio.events._get_running_loop()
    asyncio.events._set_running_loop(None)
    asyncio.set_event_loop_policy(Policy())
    asyncio.run = runners.run = run  # type: ignore[assignment]
    try:
        yield
    finally:
        asyncio.run, runners.run = old_run, old_runners_run  # type: ignore[assignment]
        asyncio.set_event_loop_policy(old_policy)
        asyncio.events._set_running_loop(prev_running)


# --- threads -------------------------------------------------------------------------------
def _patch_threads() -> None:
    import concurrent.futures as cf
    import threading

    class SyncExecutor(cf.Executor):
        """submit() turant chala deta hai. Result wahi, bas parallel nahi."""

        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
            notes.add("threads")
            f: cf.Future = cf.Future()
            try:
                f.set_result(fn(*args, **kwargs))
            except BaseException as e:  # noqa: BLE001 - future ke andar error rakhna hai
                f.set_exception(e)
            return f

    cf.ThreadPoolExecutor = SyncExecutor  # type: ignore[misc,assignment]

    def start(self: threading.Thread) -> None:
        notes.add("threads")
        self._started.set()  # type: ignore[attr-defined]
        try:
            self.run()
        finally:
            self._is_stopped = True  # type: ignore[attr-defined]

    threading.Thread.start = start  # type: ignore[method-assign]
    threading.Thread.join = lambda self, timeout=None: None  # type: ignore[method-assign]
    threading.Thread.is_alive = lambda self: False  # type: ignore[method-assign]


# --- subprocess ----------------------------------------------------------------------------
def _patch_subprocess() -> None:
    import subprocess

    def run(args, *a: Any, input: str | bytes | None = None, capture_output: bool = False, text: bool = False,
            timeout: float | None = None, **kw: Any):
        notes.add("subprocess")
        argv = list(args) if not isinstance(args, str) else args.split()
        code: str | None = None
        if "-c" in argv:
            code = argv[argv.index("-c") + 1]
        else:
            py = [x for x in argv if str(x).endswith(".py")]
            if py:
                code = open(py[-1]).read()
        if code is None:
            raise OSError("subprocess is not available in the browser")
        out, err = io.StringIO(), io.StringIO()
        stdin = io.StringIO(input.decode() if isinstance(input, bytes) else (input or ""))
        rc = 0
        old_in = sys.stdin
        try:
            sys.stdin = stdin
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                exec(compile(code, "<browser-subprocess>", "exec"), {"__name__": "__main__"})
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except BaseException as e:  # noqa: BLE001
            import traceback

            err.write("".join(traceback.format_exception(e)))
            rc = 1
        finally:
            sys.stdin = old_in
        o, er = out.getvalue(), err.getvalue()
        if not text and not kw.get("universal_newlines") and not kw.get("encoding"):
            o, er = o.encode(), er.encode()  # type: ignore[assignment]
        return subprocess.CompletedProcess(argv, rc, o if capture_output or kw.get("stdout") else None,
                                           er if capture_output or kw.get("stderr") else None)

    subprocess.run = run  # type: ignore[assignment]


# --- httpx -> XHR --------------------------------------------------------------------------
def _patch_httpx() -> None:
    try:
        import httpx
    except ImportError:  # worker ne httpx load nahi kiya: kuch patch karne ko nahi
        return
    from agentkit.llm import http as kit_http

    class XHRTransport(httpx.BaseTransport):
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            notes.add("httpx")
            headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length", "user-agent", "accept-encoding", "connection")}
            body = request.read().decode() or None
            try:
                resp = kit_http._xhr_transport(request.method, str(request.url), headers, body, 30.0)
            except kit_http.TransportError as e:
                raise httpx.ConnectError(f"{e} (browser mein sirf CORS allow karne wale hosts chalte hain)", request=request) from e
            return httpx.Response(resp.status, text=resp.text, request=request)

    httpx.HTTPTransport = XHRTransport  # type: ignore[misc,assignment]
