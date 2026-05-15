"""Tools exposed to the Claude agent. Each is a thin, audited wrapper. All
filesystem operations route through `security.is_safe_path` against the
worktree root the agent_runner was spawned with."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .security import is_safe_path  # type: ignore[import-not-found]


@dataclass
class ToolContext:
    worktree: Path
    staging: Path  # where Discord attachments live before the agent acts on them
    audit_log: Path


# -------- Tool schemas (sent to Claude) --------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": "List files and directories under a path inside the worktree. Use to explore the codebase before editing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path under the worktree. '' for root."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file inside the worktree. Path must be under scenes/, scripts/, assets/, tests/, tools/, data/, addons/, resources/, or be project.godot or .gitignore.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a text file inside the worktree, subject to the same path whitelist as read_file. Always read the file first if it exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "register_sprite",
        "description": "Move a staged Discord attachment into assets/ and register it under an object UID in data/object_registry.json. The animation key namespaces the asset (e.g. 'idle', 'run', 'jump'). Replaces any existing asset for that uid/animation pair.",
        "input_schema": {
            "type": "object",
            "properties": {
                "staging_name": {"type": "string", "description": "Filename of the attachment as reported in the prompt's 'attachments' context."},
                "uid": {"type": "string", "description": "Object UID this sprite belongs to (e.g. 'player_main', 'capsule_green')."},
                "animation": {"type": "string", "description": "Animation slot within the object (e.g. 'idle', 'run', 'absorb', 'default')."},
                "subdir": {"type": "string", "description": "Subdirectory under assets/ (e.g. 'player', 'objects')."},
            },
            "required": ["staging_name", "uid", "animation", "subdir"],
        },
    },
    {
        "name": "register_object",
        "description": "Create or update an entry in data/object_registry.json. Use to document a new game object with its UID, type, and arbitrary metadata before attaching sprites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "type": {"type": "string", "description": "e.g. 'player', 'absorbable', 'enemy', 'projectile'"},
                "metadata": {"type": "object", "description": "Free-form metadata (color, tags, scene path, etc.)"},
            },
            "required": ["uid", "type"],
        },
    },
    {
        "name": "read_object_registry",
        "description": "Read the entire object registry (data/object_registry.json).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_tests",
        "description": "Run the Godot headless test framework. Optionally filter to a single scenario. Returns the orchestrator's stdout.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario name without .json, or empty for all."},
            },
        },
    },
    {
        "name": "git_commit",
        "description": "Stage all changes inside the worktree and commit. Use one logical commit per task.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "git_push",
        "description": "Push the worktree branch to origin. Run after one or more git_commit calls.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "finish",
        "description": "Signal end of task with a short summary that will be posted back to Discord.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]


# -------- Implementations --------

def _audit(ctx: ToolContext, name: str, payload: dict[str, Any], result: str) -> None:
    rec = {"tool": name, "input": payload, "result_preview": result[:200]}
    with ctx.audit_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _safe(ctx: ToolContext, path: str) -> Path:
    ok, reason = is_safe_path(ctx.worktree, path)
    if not ok:
        raise PermissionError(f"path '{path}' rejected: {reason}")
    return (ctx.worktree / path.replace("\\", "/").lstrip("/")).resolve()


def tool_list_files(ctx: ToolContext, path: str = "") -> str:
    if path:
        target = _safe(ctx, path)
    else:
        target = ctx.worktree.resolve()
    if not target.exists():
        return f"NOT FOUND: {path}"
    if target.is_file():
        return f"FILE: {path} ({target.stat().st_size} bytes)"
    entries: list[str] = []
    for child in sorted(target.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
        if child.name in {".git", "agent", ".godot"}:
            continue
        marker = "DIR " if child.is_dir() else "FILE"
        entries.append(f"{marker} {child.name}")
    return "\n".join(entries) if entries else "(empty)"


def tool_read_file(ctx: ToolContext, path: str) -> str:
    target = _safe(ctx, path)
    if not target.exists() or not target.is_file():
        return f"NOT FOUND: {path}"
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"BINARY FILE (not readable as text): {path} ({target.stat().st_size} bytes)"


def tool_write_file(ctx: ToolContext, path: str, content: str) -> str:
    target = _safe(ctx, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return f"WROTE {path} ({len(content)} bytes)"


def tool_register_sprite(ctx: ToolContext, staging_name: str, uid: str, animation: str, subdir: str) -> str:
    src = ctx.staging / staging_name
    if not src.exists():
        return f"NOT FOUND in staging: {staging_name}"
    safe_uid = _slug(uid)
    safe_anim = _slug(animation)
    safe_sub = _slug(subdir)
    target_dir = ctx.worktree / "assets" / safe_sub
    ok, reason = is_safe_path(ctx.worktree, f"assets/{safe_sub}")
    if not ok:
        return f"REJECTED: {reason}"
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() or ".png"
    final_name = f"{safe_uid}_{safe_anim}{ext}"
    target = target_dir / final_name
    shutil.copy2(src, target)
    rel_res = f"res://assets/{safe_sub}/{final_name}"
    _update_registry(ctx, uid, sprite_slot=(animation, rel_res))
    return f"REGISTERED {rel_res} on uid='{uid}' animation='{animation}'"


def tool_register_object(ctx: ToolContext, uid: str, type: str, metadata: dict | None = None) -> str:
    _update_registry(ctx, uid, type_=type, metadata=metadata or {})
    return f"REGISTERED object uid='{uid}' type='{type}'"


def tool_read_object_registry(ctx: ToolContext) -> str:
    reg = _load_registry(ctx)
    return json.dumps(reg, ensure_ascii=False, indent=2)


def tool_run_tests(ctx: ToolContext, scenario: str = "") -> str:
    runner = ctx.worktree / "tools" / "run_tests.py"
    if not runner.exists():
        return "tools/run_tests.py not found in worktree"
    cmd = ["python", str(runner)]
    if scenario:
        cmd += ["--scenario", scenario]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        cwd=str(ctx.worktree),
    )
    out = proc.stdout or ""
    if proc.stderr:
        out += "\n--- stderr ---\n" + proc.stderr
    return out + f"\n[exit={proc.returncode}]"


def tool_git_commit(ctx: ToolContext, message: str) -> str:
    if not message.strip():
        return "REFUSED: empty commit message"
    subprocess.run(["git", "add", "-A"], cwd=str(ctx.worktree), check=True, capture_output=True)
    res = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(ctx.worktree),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (res.stdout or "") + (res.stderr or "")


def tool_git_push(ctx: ToolContext) -> str:
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(ctx.worktree),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    res = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=str(ctx.worktree),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (res.stdout or "") + (res.stderr or "")


# -------- Helpers --------

def _slug(s: str) -> str:
    s = s.strip().lower()
    out: list[str] = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-"):
            out.append(ch)
        elif ch in (" ", "."):
            out.append("_")
    return "".join(out) or "x"


def _registry_path(ctx: ToolContext) -> Path:
    return ctx.worktree / "data" / "object_registry.json"


def _load_registry(ctx: ToolContext) -> dict:
    p = _registry_path(ctx)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_registry(ctx: ToolContext, reg: dict) -> None:
    p = _registry_path(ctx)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _update_registry(
    ctx: ToolContext,
    uid: str,
    *,
    type_: str | None = None,
    metadata: dict | None = None,
    sprite_slot: tuple[str, str] | None = None,
) -> None:
    reg = _load_registry(ctx)
    entry = reg.get(uid, {})
    if type_ is not None:
        entry["type"] = type_
    if metadata is not None:
        existing_md = entry.get("metadata", {})
        existing_md.update(metadata)
        entry["metadata"] = existing_md
    if sprite_slot is not None:
        sprites = entry.get("sprites", {})
        sprites[sprite_slot[0]] = sprite_slot[1]
        entry["sprites"] = sprites
    if "uid" not in entry:
        entry["uid"] = uid
    reg[uid] = entry
    _save_registry(ctx, reg)


# Dispatch table
DISPATCH = {
    "list_files":           tool_list_files,
    "read_file":            tool_read_file,
    "write_file":           tool_write_file,
    "register_sprite":      tool_register_sprite,
    "register_object":      tool_register_object,
    "read_object_registry": tool_read_object_registry,
    "run_tests":            tool_run_tests,
    "git_commit":           tool_git_commit,
    "git_push":             tool_git_push,
}


def execute(ctx: ToolContext, name: str, args: dict[str, Any]) -> str:
    fn = DISPATCH.get(name)
    if fn is None:
        return f"UNKNOWN TOOL: {name}"
    try:
        result = fn(ctx, **args)
    except TypeError as e:
        result = f"BAD ARGS for {name}: {e}"
    except PermissionError as e:
        result = f"DENIED: {e}"
    except Exception as e:  # noqa: BLE001
        result = f"ERROR in {name}: {type(e).__name__}: {e}"
    _audit(ctx, name, args, result)
    return result
