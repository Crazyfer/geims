"""Subprocess that the Discord bot spawns for each command. Spawns the Claude
CLI as a child process using the 'gamedev' agent definition, parses the
streamed JSONL output, and writes a single JSON line to stdout on completion.

Invoked as:
    python -m agent.agent_runner --task <text> [--attachments file1 file2 ...]
                                 [--session-id <uuid>]

The Claude CLI inherits the user's local authentication (~/.claude/), so no
ANTHROPIC_API_KEY is needed.

Session continuity: when --session-id is provided the CLI resumes the existing
session, giving the agent full context of previous messages in that channel.
The session_id emitted by the CLI in the init event is returned alongside the
result so the caller can store it for the next invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")


def build_prompt(task: str, attachments: list[str]) -> str:
    lines = [task]
    if attachments:
        lines.append("")
        lines.append("Attached files (available in data/staging/ inside the worktree):")
        for a in attachments:
            lines.append(f"  - data/staging/{a}")
        lines.append("")
        lines.append("You can read these files with the Read tool. To register a sprite, use:")
        lines.append("  python agent/scripts/register_sprite.py --staging-name <filename> --uid <uid> --animation <anim> --subdir <subdir>")
    return "\n".join(lines)


def run_agent(task: str, attachments: list[str], session_id: str | None = None) -> dict:
    worktree = Path(os.environ.get("AGENT_WORKTREE", ".")).resolve()
    if not worktree.exists():
        return {"ok": False, "summary": f"worktree not found at {worktree}"}

    prompt = build_prompt(task, attachments)
    timeout = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "300"))

    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--agent", "gamedev",
        "--output-format", "stream-json",
        "--model", CLAUDE_MODEL,
        "--verbose",
        "--max-turns", "30",
        "--permission-mode", "bypassPermissions",
    ]

    if session_id:
        cmd += ["--resume", session_id]

    env = os.environ.copy()

    # On Windows, .cmd/.bat wrappers need cmd.exe to execute. We use
    # ["cmd.exe", "/c", ...] instead of shell=True so that we keep full
    # control of encoding (shell=True inherits the system codepage).
    if sys.platform == "win32" and CLAUDE_BIN.endswith((".cmd", ".bat")):
        cmd = ["cmd.exe", "/c"] + cmd

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worktree),
            env=env,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "summary": f"claude CLI not found at '{CLAUDE_BIN}'. Install with: npm install -g @anthropic-ai/claude-code"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "summary": f"claude CLI timed out after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "summary": f"claude CLI error: {type(e).__name__}: {e}"}

    # Parse JSONL stdout — extract session_id from init event and result from
    # the last result event.  Decode as UTF-8 (the CLI always outputs UTF-8
    # regardless of the Windows console codepage).
    stdout = proc.stdout.decode("utf-8", errors="replace") if isinstance(proc.stdout, bytes) else (proc.stdout or "")
    stderr = proc.stderr.decode("utf-8", errors="replace") if isinstance(proc.stderr, bytes) else (proc.stderr or "")

    result_text = None
    cli_session_id = None
    num_lines = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        num_lines += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            cli_session_id = event.get("session_id")
        if event.get("type") == "result":
            result_text = event.get("result", "")
            cli_session_id = event.get("session_id") or cli_session_id

    if result_text is not None:
        out = {"ok": True, "summary": result_text}
        if cli_session_id:
            out["session_id"] = cli_session_id
        return out

    # Fallback: if no result event found, check exit code and grab whatever
    # text output we can.
    stderr_tail = stderr[-800:]
    stdout_tail = stdout[-800:]

    if proc.returncode == 0:
        fallback = stdout.strip().splitlines()
        last = fallback[-1] if fallback else ""
        try:
            evt = json.loads(last)
            out = {"ok": True, "summary": evt.get("result", evt.get("text", "(no summary)"))}
        except (json.JSONDecodeError, AttributeError):
            out = {"ok": True, "summary": last or "(agent finished without summary)"}
        if cli_session_id:
            out["session_id"] = cli_session_id
        return out

    return {"ok": False, "summary": f"claude CLI exited with code {proc.returncode} ({num_lines} lines parsed). stderr tail:\n{stderr_tail}\nstdout tail:\n{stdout_tail}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--attachments", nargs="*", default=[])
    parser.add_argument("--session-id", default=None, help="Resume an existing CLI session")
    args = parser.parse_args()

    result = run_agent(args.task, args.attachments, session_id=args.session_id)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
