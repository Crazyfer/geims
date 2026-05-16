#!/usr/bin/env python3
"""
Runs Godot test scenarios in headless mode and reports pass/fail.

Usage:
  python tools/run_tests.py                     # runs every scenario
  python tools/run_tests.py --scenario smoke    # runs tests/scenarios/smoke.json

Locating Godot:
  - Set GODOT_BIN env var to the full path of the Godot executable, OR
  - Place godot / godot.exe on PATH
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from shutil import which

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "tests" / "scenarios"
TEST_RUNNER_RES = "res://tests/test_runner.tscn"
PER_TEST_TIMEOUT = 60  # seconds


def find_godot() -> str:
    env_path = os.environ.get("GODOT_BIN")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return str(p)
        sys.exit(f"GODOT_BIN points to {env_path} which does not exist.")
    for name in ("godot", "godot.exe", "Godot.exe", "Godot_v4-stable_win64.exe"):
        p = which(name)
        if p:
            return p
    sys.exit(
        "Could not locate Godot. Set GODOT_BIN to the full path of the "
        "Godot executable (e.g. C:\\Tools\\Godot.exe) and rerun."
    )


def list_scenarios() -> list[Path]:
    if not SCENARIOS_DIR.exists():
        sys.exit(f"No scenarios directory at {SCENARIOS_DIR}")
    return sorted(SCENARIOS_DIR.glob("*.json"))


def run_scenario(godot_bin: str, scenario: Path, *, windowed: bool, linger: float) -> tuple[bool, str]:
    rel = f"res://tests/scenarios/{scenario.name}"
    cmd: list[str] = [godot_bin]
    if not windowed:
        cmd.append("--headless")
    cmd += ["--path", str(PROJECT_ROOT), TEST_RUNNER_RES, "--", "--scenario", rel]
    if linger > 0.0:
        cmd += ["--linger", f"{linger:.2f}"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PER_TEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        return False, f"TIMEOUT after {PER_TEST_TIMEOUT}s\n{e.stdout or ''}"

    output = proc.stdout or ""
    if proc.stderr:
        output += "\n--- stderr ---\n" + proc.stderr
    # Use stdout summary as authoritative signal; Godot may exit non-zero on
    # Windows headless due to Vulkan/display init errors unrelated to test outcome.
    m = SUMMARY_RE.search(output)
    passed = m is not None and m.group(1) == "PASS"
    return passed, output


SUMMARY_RE = re.compile(r"\[TEST\][^\n]*\bsummary\b (\w+) (\d+)/(\d+)")
FAIL_DETAIL_RE = re.compile(r"\[TEST\][^\n]*fail_detail\s*(.*)")


def short_report(output: str) -> str:
    lines: list[str] = []
    m = SUMMARY_RE.search(output)
    if m:
        status, p, t = m.group(1), m.group(2), m.group(3)
        lines.append(f"  summary: {status} {p}/{t}")
    for fm in FAIL_DETAIL_RE.finditer(output):
        lines.append(f"  fail   : {fm.group(1).strip()}")
    if not lines:
        lines.append("  (no [TEST] summary captured)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", help="Run only this scenario (without .json)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Stream Godot stdout/stderr")
    parser.add_argument("--windowed", action="store_true", help="Open Godot's window instead of running headless")
    parser.add_argument("--linger", type=float, default=0.0, help="Seconds to wait before quitting after assertions")
    args = parser.parse_args()
    effective_linger = args.linger if args.linger > 0.0 else (3.0 if args.windowed else 0.0)

    godot_bin = find_godot()
    print(f"godot: {godot_bin}")
    print(f"project: {PROJECT_ROOT}\n")

    scenarios = list_scenarios()
    if args.scenario:
        scenarios = [s for s in scenarios if s.stem == args.scenario]
        if not scenarios:
            sys.exit(f"No scenario matched: {args.scenario}")

    passed_n = 0
    failed: list[str] = []

    for scenario in scenarios:
        print(f"=== {scenario.stem} ===")
        ok, output = run_scenario(godot_bin, scenario, windowed=args.windowed, linger=effective_linger)
        if args.verbose:
            print(output)
        else:
            print(short_report(output))
        if ok:
            passed_n += 1
        else:
            failed.append(scenario.stem)
        print()

    total = len(scenarios)
    print(f"=== results ===")
    print(f"passed {passed_n}/{total}")
    if failed:
        print(f"failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
