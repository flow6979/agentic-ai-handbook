"""LLM ka likha code alag process mein, timeout ke saath chalao.

WARNING: `subprocess` + temp dir asli sandbox NAHI hai. Code file system/network access kar
sakta hai. Production mein Docker (no network, read-only FS, CPU/mem limits), gVisor,
Firecracker, ya E2B/Modal jaise hosted sandboxes use karo. Yahan hum sirf teaching ke liye:
- alag process (`-I` isolated mode: user site-packages / env vars ignore)
- timeout (infinite loop se bachao)
- temp directory (cwd)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestRun:
    passed: bool
    output: str
    n_failed: int


def build_harness(code: str, tests: list[str]) -> str:
    """Code + har test ko try/except mein lapeto taaki har failing test report ho, sirf pehla nahi."""
    lines = [code, "", "_failed = 0"]
    for t in tests:
        lines += [
            "try:",
            f"    {t}",
            f"    print('PASS: ' + {t!r})",
            "except Exception as _e:",
            "    _failed += 1",
            f"    print('FAIL: ' + {t!r} + ' -> ' + type(_e).__name__ + ': ' + str(_e))",
        ]
    lines += ["import sys", "sys.exit(1 if _failed else 0)"]
    return "\n".join(lines)


def run_tests(code: str, tests: list[str], timeout: float = 5.0) -> TestRun:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "candidate.py"
        path.write_text(build_harness(code, tests))
        try:
            proc = subprocess.run([sys.executable, "-I", str(path)], cwd=d, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            return TestRun(False, f"TIMEOUT: code ran longer than {timeout}s (infinite loop?)", len(tests))
    out = (proc.stdout + proc.stderr).strip()
    n_failed = out.count("FAIL: ")
    if proc.returncode != 0 and n_failed == 0:  # syntax error / crash before tests ran
        n_failed = len(tests)
    return TestRun(proc.returncode == 0, out[-3000:], n_failed)
