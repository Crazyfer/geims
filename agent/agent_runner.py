"""Subprocess that the Discord bot spawns for each command. Loads the system
prompt, runs the Anthropic tool-use loop, and writes a single JSON line to
stdout on completion.

Invoked as:
    python -m agent.agent_runner --task <text> [--attachments file1 file2 ...]

stdin/stderr from tools are captured into an audit log; only the final
summary is returned on stdout under the key "summary".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic

# Make 'agent' importable when invoked as a module from elsewhere.
PKG_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG_ROOT.parent))

from agent import tools as t  # noqa: E402

MODEL = "claude-sonnet-4-5"  # change to "claude-sonnet-4-6" once your Anthropic project has access
MAX_ITERATIONS = 30
MAX_TOKENS = 4096


def load_system_prompt() -> str:
    return (PKG_ROOT / "system_prompt.md").read_text(encoding="utf-8")


def build_user_message(task: str, attachments: list[str]) -> str:
    lines = [f"Task: {task}"]
    if attachments:
        lines.append("")
        lines.append("Attachments (staged, reference by these names in register_sprite):")
        for a in attachments:
            lines.append(f"  - {a}")
    return "\n".join(lines)


def run_agent(task: str, attachments: list[str]) -> dict:
    worktree = Path(os.environ.get("AGENT_WORKTREE", ".")).resolve()
    if not worktree.exists():
        return {"ok": False, "summary": f"worktree not found at {worktree}"}

    audit_log = PKG_ROOT / "data" / "audit.log"
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    staging = PKG_ROOT / "data" / "staging"

    ctx = t.ToolContext(worktree=worktree, staging=staging, audit_log=audit_log)
    client = Anthropic()

    messages: list[dict] = [
        {"role": "user", "content": build_user_message(task, attachments)},
    ]
    system_prompt = load_system_prompt()

    summary: str | None = None
    iterations = 0
    started = time.time()
    timeout = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "300"))

    while iterations < MAX_ITERATIONS:
        if time.time() - started > timeout:
            return {"ok": False, "summary": f"agent timed out after {timeout}s"}

        iterations += 1
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=t.TOOL_SCHEMAS + [_FINISH_SCHEMA],
                messages=messages,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "summary": f"Claude API error: {type(e).__name__}: {e}"}

        assistant_content = [_block_to_dict(b) for b in resp.content]
        messages.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason == "end_turn" and not any(b.get("type") == "tool_use" for b in assistant_content):
            text = _extract_text(assistant_content)
            return {"ok": True, "summary": text or "(agent ended without summary)"}

        tool_results: list[dict] = []
        for block in assistant_content:
            if block.get("type") != "tool_use":
                continue
            name = block["name"]
            args = block.get("input", {}) or {}
            if name == "finish":
                summary = str(args.get("summary", ""))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "OK",
                })
                continue
            result = t.execute(ctx, name, args)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": result,
            })

        if summary is not None:
            return {"ok": True, "summary": summary}

        if not tool_results:
            return {"ok": True, "summary": _extract_text(assistant_content) or "(no tool calls)"}

        messages.append({"role": "user", "content": tool_results})

    return {"ok": False, "summary": f"agent hit max iterations ({MAX_ITERATIONS})"}


_FINISH_SCHEMA = {
    "name": "finish",
    "description": "End the task. Provide a short summary that will be posted back to Discord.",
    "input_schema": {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    },
}


def _block_to_dict(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": block.type}


def _extract_text(blocks: list[dict]) -> str:
    parts = [b["text"] for b in blocks if b.get("type") == "text"]
    return "\n".join(parts).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--attachments", nargs="*", default=[])
    args = parser.parse_args()

    result = run_agent(args.task, args.attachments)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
