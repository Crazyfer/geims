"""Defense layer for the Discord agent: prompt-injection regex, channel/user
auth, and filesystem path whitelist. None of these alone is sufficient — they
are layered together with a strict system prompt and a tool whitelist."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PROMPT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bignore\s+(all\s+)?(previous|above|earlier|prior)\s+(instructions?|prompts?|rules?)",
        r"\bdisregard\s+(all\s+)?(previous|above|earlier|prior)\s+(instructions?|prompts?|rules?)",
        r"\bforget\s+(everything|all|what|your)\b",
        r"\b(reveal|show|print|leak|dump)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)",
        r"\b(you\s+are\s+now|from\s+now\s+on\s+you\s+are|act\s+as|roleplay\s+as|pretend\s+to\s+be|simulate\s+being)\b",
        r"\bdeveloper\s+mode\b",
        r"\bjailbreak\b",
        r"\bDAN\s+mode\b",
        r"\b(disable|bypass|override|skip)\s+(safety|filter|guard|restriction|guardrail)s?\b",
        r"\b(sudo|admin|root)\s+(mode|access|prompt)\b",
        r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|###\s*Instruction",
        r"\bnew\s+(system|developer)\s+(prompt|message|instructions?)\b",
        # Spanish variants
        r"\bignora\s+(las|todas\s+las|todo|lo\s+anterior)\b",
        r"\bolvida\s+(todo|lo\s+anterior|tus\s+instrucciones)\b",
        r"\bahora\s+eres\b",
        r"\bact[uú]a\s+como\b",
        r"\bmodo\s+(desarrollador|admin|sin\s+filtros?)\b",
        r"\b(revela|muestra|imprime|filtra)\s+(tu\s+)?(prompt|instrucciones|reglas)\s+(del?\s+)?sistema",
    ]
]


@dataclass
class GuardVerdict:
    allowed: bool
    reason: str = ""
    matched_pattern: str = ""


def check_prompt_injection(text: str) -> GuardVerdict:
    """Reject the message if it matches any known injection pattern."""
    if not text:
        return GuardVerdict(True)
    for pat in PROMPT_INJECTION_PATTERNS:
        m = pat.search(text)
        if m:
            return GuardVerdict(
                allowed=False,
                reason="message matched a prompt-injection pattern and was rejected",
                matched_pattern=pat.pattern,
            )
    return GuardVerdict(True)


def is_authorized(
    user_id: int,
    user_role_ids: set[int],
    allowed_user_ids: set[int],
    allowed_role_ids: set[int],
) -> bool:
    if user_id in allowed_user_ids:
        return True
    if allowed_role_ids and (user_role_ids & allowed_role_ids):
        return True
    return False


# Paths inside the worktree the agent may touch. Anything else (agent/, .git/,
# .env, dotfiles) is rejected — both reads and writes.
WRITABLE_PREFIXES: tuple[str, ...] = (
    "scenes",
    "scripts",
    "assets",
    "tests",
    "tools",
    "data",
    "addons",
    "resources",
)
WRITABLE_ROOT_FILES: frozenset[str] = frozenset({"project.godot", ".gitignore"})


def is_safe_path(worktree_root: Path, candidate: str) -> tuple[bool, str]:
    """Resolve `candidate` against the worktree and verify it stays inside one
    of the whitelisted prefixes. Returns (ok, reason)."""
    if not candidate:
        return False, "empty path"

    raw = candidate.replace("\\", "/").lstrip("/")
    if ".." in raw.split("/"):
        return False, "path traversal not allowed"
    if raw.startswith("."):
        return False, "dotfile/dotdir paths are not allowed"

    abs_target = (worktree_root / raw).resolve()
    try:
        abs_target.relative_to(worktree_root.resolve())
    except ValueError:
        return False, "path escapes the worktree"

    rel = abs_target.relative_to(worktree_root.resolve())
    parts = rel.parts
    if not parts:
        return False, "must point at a file, not the root"
    if parts[0] == "agent" or parts[0] == ".git":
        return False, f"{parts[0]}/ is off-limits to the agent"
    if parts[0] in WRITABLE_PREFIXES:
        return True, ""
    if len(parts) == 1 and parts[0] in WRITABLE_ROOT_FILES:
        return True, ""
    return False, f"prefix '{parts[0]}' is not in the writable whitelist"
