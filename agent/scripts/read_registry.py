#!/usr/bin/env python3
"""Dump the object registry (data/object_registry.json) to stdout.
Called by the Claude CLI agent via Bash.

Usage:
    python agent/scripts/read_registry.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PKG_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PKG_ROOT.parent))

from agent.tools import ToolContext, _load_registry  # noqa: E402
import json


def main() -> int:
    worktree = Path(os.environ.get("AGENT_WORKTREE", os.getcwd())).resolve()
    staging = PKG_ROOT / "data" / "staging"
    audit_log = PKG_ROOT / "data" / "audit.log"

    ctx = ToolContext(worktree=worktree, staging=staging, audit_log=audit_log)
    reg = _load_registry(ctx)
    print(json.dumps(reg, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
