"""`engine check`: ruff + pytest + replay integrity + gitleaks. Run before every commit (CLAUDE.md)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from engine.contracts import Cassette
from engine.llm.client import CassetteStore, hash_record
from engine.llm.pricing import ROOT

Result = tuple[bool, str]


def _run(cmd: list[str]) -> Result:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0, "\n".join(out[-15:])


def ruff() -> Result:
    ok1, out1 = _run([sys.executable, "-m", "ruff", "check", "src", "tests"])
    ok2, out2 = _run([sys.executable, "-m", "ruff", "format", "--check", "src", "tests"])
    return ok1 and ok2, f"{out1}\n{out2}"


def pytest() -> Result:
    return _run([sys.executable, "-m", "pytest", "-q"])


def replay_integrity() -> Result:
    """Cassettes are self-consistent, every recorded call has a cassette, and smoke replays exactly."""
    store = CassetteStore()
    problems: list[str] = []
    hashes: set[str] = set()
    for path in store.all():
        try:
            c = Cassette.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{path.name}: unreadable ({e.__class__.__name__})")
            continue
        if path.stem != c.request_hash or hash_record(c.request) != c.request_hash:
            problems.append(f"{path.name}: request hash mismatch")
        hashes.add(c.request_hash)

    runs = ROOT / "runs"
    referenced = 0
    for log in [*runs.glob("*/calls.jsonl"), *runs.glob("*/jev.jsonl")]:
        for line in log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            h = row["request_hash"]
            if row.get("error"):
                continue  # failed API calls return nothing to record
            referenced += 1
            if h not in hashes:
                problems.append(f"{log.parent.name}: replay miss for {h[:12]}")

    smoke_msg = "no runs/smoke.json yet"
    from engine import smoke

    if smoke.SMOKE_JSON.exists():
        stored = json.loads(smoke.SMOKE_JSON.read_text(encoding="utf-8"))
        try:
            report, _, _ = smoke.run("replay")
        except Exception as e:  # noqa: BLE001 - any replay failure is an integrity failure
            problems.append(f"smoke replay failed: {e.__class__.__name__}: {e}")
        else:
            if smoke.comparable(report.checks) != smoke.comparable(stored["checks"]):
                problems.append("smoke replay does not reproduce runs/smoke.json checks exactly")
            else:
                smoke_msg = f"smoke replay reproduces {stored['run_id']} exactly"
    summary = f"{len(hashes)} cassettes, {referenced} recorded calls referenced; {smoke_msg}"
    return not problems, "\n".join([summary, *problems[:20]])


def _gitleaks_binary() -> str | None:
    found = shutil.which("gitleaks")
    if found:
        return found
    cache = Path.home() / ".cache" / "pre-commit"
    for pattern in ("repo*/golangenv-*/bin/gitleaks.exe", "repo*/golangenv-*/bin/gitleaks"):
        hits = sorted(cache.glob(pattern))
        if hits:
            return str(hits[0])
    return None


def gitleaks() -> Result:
    binary = _gitleaks_binary()
    if binary is None:
        return (
            False,
            "gitleaks not found: run `uv run pre-commit install --install-hooks` (never skipped silently)",
        )
    ok_canary, out_canary = _gitleaks_canary(binary)
    ok_hist, out_hist = _run([binary, "git", "--redact", "--no-banner", str(ROOT)])
    ok_staged, out_staged = _run([sys.executable, "-m", "pre_commit", "run", "gitleaks", "--all-files"])
    out = f"canary: {out_canary}\nhistory: {out_hist}\nstaged: {out_staged}"
    return ok_canary and ok_hist and ok_staged, out


def _gitleaks_canary(binary: str) -> Result:
    """Self-test: freshly generated fake Anthropic/OpenRouter keys must both be detected with our config."""
    import secrets
    import string
    import tempfile

    alnum = string.ascii_letters + string.digits
    fake_anthropic = "sk-ant-api03-" + "".join(secrets.choice(alnum) for _ in range(93)) + "AA"
    fake_openrouter = "sk-or-v1-" + secrets.token_hex(32)
    with tempfile.TemporaryDirectory() as d:
        Path(d, "canary.env").write_text(f"A={fake_anthropic}\nB={fake_openrouter}\n", encoding="utf-8")
        cfg = str(ROOT / ".gitleaks.toml")
        report = Path(d, "report.json")
        _run([binary, "dir", "--no-banner", "--redact", "-c", cfg, "-r", str(report), "-f", "json", d])
        found = (
            {f["RuleID"] for f in json.loads(report.read_text(encoding="utf-8"))}
            if report.exists()
            else set()
        )
    want = {"anthropic-api-key", "openrouter-api-key"}
    return want <= found, f"detected {sorted(found)}"


STEPS: list[tuple[str, Callable[[], Result]]] = [
    ("ruff", ruff),
    ("pytest", pytest),
    ("replay integrity", replay_integrity),
    ("gitleaks", gitleaks),
]


def run_all() -> bool:
    all_ok = True
    for name, fn in STEPS:
        ok, out = fn()
        all_ok &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok or name in ("replay integrity",):
            for line in out.splitlines():
                print(f"    {line}")
    print("engine check: " + ("GREEN" if all_ok else "RED"))
    return all_ok
