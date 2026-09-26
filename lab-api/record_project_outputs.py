"""Browser mein na chal sakne wale projects ka asli offline run record karo (website pe replay ke liye).

Kuch projects ko servers / subprocess / background threads chahiye (MCP stdio, FastAPI TestClient,
uvicorn). Browser (Pyodide) mein yeh sambhav nahi. Unke liye hum yahan, normal Python mein, wahi
command chalate hain jo terminal mein chalti:

    python <project>/main.py --offline [default_args]

aur har output line (timing ke saath) `labapi/data/project_replays.json` mein save karte hain.
Website use "Replay of a real local run" badge ke saath line by line chalati hai.

    .venv/bin/python lab-api/record_project_outputs.py            # saare replay projects
    .venv/bin/python lab-api/record_project_outputs.py 07-mcp     # sirf matching
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "lab-api/labapi/projects.json"
OUT = ROOT / "lab-api/labapi/data/project_replays.json"


def record(project: str, info: dict) -> dict:
    main = ROOT / info.get("main", f"{project}/main.py")
    rec_cfg = info.get("record") or {}
    args = ["--offline", *info.get("default_args", [])]
    cmd = [sys.executable, "-u", main.name, *args]
    if rec_cfg.get("foreground"):  # e.g. server background mein, yeh client foreground mein
        cmd = [sys.executable, "-u", *rec_cfg["foreground"]]
    env = {**os.environ, "AGENT_VERBOSE": "1", "PYTHONUNBUFFERED": "1"}
    t0 = time.perf_counter()
    bg = None
    if rec_cfg.get("background"):  # "Terminal 1": server
        bg = subprocess.Popen([sys.executable, "-u", *rec_cfg["background"]], cwd=main.parent, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(rec_cfg.get("wait_s", 2.5))
    proc = subprocess.Popen(cmd, cwd=main.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.PIPE, text=True)
    lines: list[dict] = []
    lock = threading.Lock()

    def pump(stream, name):
        for line in stream:
            with lock:
                lines.append({"t": round((time.perf_counter() - t0) * 1000), "stream": name, "text": line.rstrip("\n")})

    threads = [threading.Thread(target=pump, args=(proc.stdout, "stdout")), threading.Thread(target=pump, args=(proc.stderr, "stderr"))]
    for th in threads:
        th.start()
    proc.stdin.write(info.get("default_stdin", ""))
    proc.stdin.close()
    rc = proc.wait(timeout=120)
    for th in threads:
        th.join()
    if bg:
        bg.terminate()
        server_out = bg.communicate(timeout=10)[0]
        for l in server_out.splitlines():
            lines.append({"t": round((time.perf_counter() - t0) * 1000), "stream": "stderr", "text": f"[server] {l}"})
    lines.sort(key=lambda l: l["t"])
    shown = " ".join(rec_cfg["foreground"]) if rec_cfg.get("foreground") else f"{project}/main.py {' '.join(args)}"
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": rec_cfg.get("label") or ((f"python {' '.join(rec_cfg['background'])}  &&  " if bg else "") + f"python {shown}"),
        "python": platform.python_version(),
        "exit_code": rc,
        "ms": round((time.perf_counter() - t0) * 1000),
        "lines": lines,
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    filters = sys.argv[1:]
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    for project, info in manifest.items():
        if info.get("browser") != "replay" or (filters and not any(f in project for f in filters)):
            continue
        rec = record(project, info)
        status = "ok" if rec["exit_code"] == 0 else f"exit {rec['exit_code']}"
        print(f"{status:8} {project}  lines={len(rec['lines'])}  {rec['ms']} ms")
        existing[project] = rec
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(existing, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
