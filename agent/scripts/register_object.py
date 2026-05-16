#!/usr/bin/env python3
"""Create or update an entry in data/object_registry.json.
Called by the Claude CLI agent via Bash.

Usage:
    python agent/scripts/register_object.py \
        --uid <uid> --type <type> [--metadata '{"key":"val"}']
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PKG_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PKG_ROOT.parent))

from agent.tools import ToolContext, _update_registry, _audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Register or update a game object")
    parser.add_argument("--uid", required=True, help="Object UID (e.g. player_main)")
    parser.add_argument("--type", required=True, dest="obj_type", help="Object type (e.g. player, enemy)")
    parser.add_argument("--metadata", default="{}", help="JSON object with free-form metadata")
    args = parser.parse_args()

    try:
        metadata = json.loads(args.metadata)
    except json.JSONDecodeError as e:
        print(f"Invalid --metadata JSON: {e}", file=sys.stderr)
        return 1

    worktree = Path(os.environ.get("AGENT_WORKTREE", os.getcwd())).resolve()
    staging = PKG_ROOT / "data" / "staging"
    audit_log = PKG_ROOT / "data" / "audit.log"
    audit_log.parent.mkdir(parents=True, exist_ok=True)

    ctx = ToolContext(worktree=worktree, staging=staging, audit_log=audit_log)
    _update_registry(ctx, args.uid, type_=args.obj_type, metadata=metadata)
    _audit(ctx, "register_object", {
        "uid": args.uid,
        "type": args.obj_type,
        "metadata": metadata,
    }, f"REGISTERED object uid='{args.uid}'")

    print(f"REGISTERED object uid='{args.uid}' type='{args.obj_type}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
