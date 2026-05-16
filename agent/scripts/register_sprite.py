#!/usr/bin/env python3
"""Move a staged Discord attachment into assets/ and register it in the object
registry. Called by the Claude CLI agent via Bash.

Usage:
    python agent/scripts/register_sprite.py \
        --staging-name <filename> --uid <uid> --animation <anim> --subdir <subdir>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Allow imports from the agent package when invoked from the worktree root.
SCRIPT_DIR = Path(__file__).resolve().parent
PKG_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PKG_ROOT.parent))

from agent.security import is_safe_path  # noqa: E402
from agent.tools import (  # noqa: E402
    ToolContext,
    _slug,
    _update_registry,
    _audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a staged sprite into assets/")
    parser.add_argument("--staging-name", required=True, help="Filename in agent/data/staging/")
    parser.add_argument("--uid", required=True, help="Object UID (e.g. player_main)")
    parser.add_argument("--animation", required=True, help="Animation slot (e.g. idle, run)")
    parser.add_argument("--subdir", required=True, help="Subdirectory under assets/ (e.g. player)")
    args = parser.parse_args()

    worktree = Path(os.environ.get("AGENT_WORKTREE", os.getcwd())).resolve()
    staging = PKG_ROOT / "data" / "staging"
    audit_log = PKG_ROOT / "data" / "audit.log"
    audit_log.parent.mkdir(parents=True, exist_ok=True)

    ctx = ToolContext(worktree=worktree, staging=staging, audit_log=audit_log)

    # Check both the agent's staging dir and the worktree's staging dir.
    src = staging / args.staging_name
    if not src.exists():
        wt_staging = worktree / "data" / "staging" / args.staging_name
        if wt_staging.exists():
            src = wt_staging
        else:
            print(f"NOT FOUND in staging: {args.staging_name}", file=sys.stderr)
            return 1

    safe_uid = _slug(args.uid)
    safe_anim = _slug(args.animation)
    safe_sub = _slug(args.subdir)

    ok, reason = is_safe_path(worktree, f"assets/{safe_sub}")
    if not ok:
        print(f"REJECTED: {reason}", file=sys.stderr)
        return 1

    target_dir = worktree / "assets" / safe_sub
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = src.suffix.lower() or ".png"
    final_name = f"{safe_uid}_{safe_anim}{ext}"
    target = target_dir / final_name
    shutil.copy2(src, target)

    rel_res = f"res://assets/{safe_sub}/{final_name}"
    _update_registry(ctx, args.uid, sprite_slot=(args.animation, rel_res))
    _audit(ctx, "register_sprite", {
        "staging_name": args.staging_name,
        "uid": args.uid,
        "animation": args.animation,
        "subdir": args.subdir,
    }, f"REGISTERED {rel_res}")

    print(f"REGISTERED {rel_res} on uid='{args.uid}' animation='{args.animation}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
