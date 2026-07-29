"""Run every consumer's tests against the uilab checkout you have right now.

Editable installs make "always the newest version" true by construction, and
that is exactly why this exists: the update problem is solved and the BREAKAGE
problem takes its place. A change here is live in every consumer immediately,
and without this nothing tells you which one it broke until you open that app.

    uv run python tools/check_consumers.py            # all
    uv run python tools/check_consumers.py sm64_tracker

A missing checkout is SKIPPED, not failed — a machine that has not cloned a
consumer is not a broken machine. A consumer whose venv is missing is REPORTED,
because that one is a setup someone abandoned half-done.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load() -> list[dict]:
    return json.loads((ROOT / "consumers.json").read_text(encoding="utf-8"))["consumers"]


def check(entry: dict) -> tuple[str, str]:
    """Return (status, detail). status in {ok, failed, skipped, unconfigured}."""
    path = (ROOT / entry["path"]).resolve()
    if not path.is_dir():
        return "skipped", f"no checkout at {path}"
    python = path / entry["python"]
    if not python.exists():
        return "unconfigured", (
            f"no interpreter at {python} — install it editable:\n"
            f"      uv pip install --python \"{python}\" -e \"{ROOT}\" -e . pytest")
    proc = subprocess.run([str(python), *entry["verify"]], cwd=path,
                          capture_output=True, text=True)
    if proc.returncode == 0:
        return "ok", (proc.stdout.strip().splitlines() or [""])[-1]
    tail = "\n      ".join((proc.stdout + proc.stderr).strip().splitlines()[-12:])
    return "failed", tail


def main(argv: list[str]) -> int:
    wanted = set(argv[1:])
    consumers = [c for c in load() if not wanted or c["name"] in wanted]
    if not consumers:
        print(f"no consumer matches {sorted(wanted)}")
        return 2

    worst = 0
    for entry in consumers:
        status, detail = check(entry)
        mark = {"ok": "PASS", "failed": "FAIL", "skipped": "skip",
                "unconfigured": "SETUP"}[status]
        print(f"[{mark}] {entry['name']}: {detail}")
        if status == "failed":
            worst = 1
        elif status == "unconfigured" and worst == 0:
            worst = 0        # not a failure: nothing has been claimed about it
    if worst:
        print("\nA consumer is red against this working tree. Editable installs "
              "mean it is red RIGHT NOW, not at some future update.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
