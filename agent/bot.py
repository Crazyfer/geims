"""Discord bot. Listens on whitelisted channels, runs each command through
the prompt-injection guard, stages any attachments, then spawns
agent_runner.py as an isolated subprocess and posts its summary back.

Run:
    python -m agent.bot
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
import uuid
from pathlib import Path

import aiohttp
import discord
from dotenv import load_dotenv

from agent.security import check_prompt_injection, is_authorized


HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")


def _parse_int_csv(name: str) -> set[int]:
    raw = os.environ.get(name, "")
    out: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            out.add(int(piece))
    return out


ALLOWED_CHANNEL_IDS = _parse_int_csv("DISCORD_ALLOWED_CHANNEL_IDS")
ALLOWED_USER_IDS    = _parse_int_csv("DISCORD_ALLOWED_USER_IDS")
ALLOWED_ROLE_IDS    = _parse_int_csv("DISCORD_ALLOWED_ROLE_IDS")
WORKTREE            = Path(os.environ.get("AGENT_WORKTREE", "")).resolve() if os.environ.get("AGENT_WORKTREE") else None
TIMEOUT_SECONDS     = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "300"))
STAGING             = HERE / "data" / "staging"


def _fatal_config_check() -> None:
    missing = []
    if not os.environ.get("DISCORD_BOT_TOKEN"):
        missing.append("DISCORD_BOT_TOKEN")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not ALLOWED_CHANNEL_IDS:
        missing.append("DISCORD_ALLOWED_CHANNEL_IDS")
    if not ALLOWED_USER_IDS and not ALLOWED_ROLE_IDS:
        missing.append("DISCORD_ALLOWED_USER_IDS or DISCORD_ALLOWED_ROLE_IDS")
    if not WORKTREE or not WORKTREE.exists():
        missing.append("AGENT_WORKTREE (run agent/setup_worktree.ps1 first)")
    if missing:
        sys.stderr.write("Missing required configuration:\n  - " + "\n  - ".join(missing) + "\n")
        sys.exit(2)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)


async def _stage_attachments(message: discord.Message) -> list[str]:
    if not message.attachments:
        return []
    STAGING.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    async with aiohttp.ClientSession() as session:
        for att in message.attachments:
            safe_base = "".join(c for c in att.filename if c.isalnum() or c in ".-_") or "att"
            staged_name = f"{uuid.uuid4().hex[:8]}_{safe_base}"
            target = STAGING / staged_name
            async with session.get(att.url) as resp:
                resp.raise_for_status()
                data = await resp.read()
            target.write_bytes(data)
            saved.append(staged_name)
    return saved


async def _run_agent(task: str, attachments: list[str]) -> dict:
    env = os.environ.copy()
    cmd = [
        sys.executable, "-m", "agent.agent_runner",
        "--task", task,
    ]
    if attachments:
        cmd += ["--attachments", *attachments]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(HERE.parent),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS + 30)
    except asyncio.TimeoutError:
        proc.kill()
        return {"ok": False, "summary": "agent subprocess killed (host-side timeout)"}

    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    last_line = text.splitlines()[-1] if text else "{}"
    try:
        result = json.loads(last_line)
    except json.JSONDecodeError:
        err = (stderr or b"").decode("utf-8", errors="replace")[-800:]
        return {"ok": False, "summary": f"agent returned non-JSON. stderr tail:\n{err}"}
    return result


def _chunk_for_discord(text: str, limit: int = 1900) -> list[str]:
    chunks: list[str] = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks or [""]


@client.event
async def on_ready() -> None:
    print(f"Bot online as {client.user} (id={client.user.id if client.user else '?'})")
    print(f"Allowed channels: {sorted(ALLOWED_CHANNEL_IDS)}")
    print(f"Allowed users:    {sorted(ALLOWED_USER_IDS)}")
    print(f"Allowed roles:    {sorted(ALLOWED_ROLE_IDS)}")
    print(f"Worktree:         {WORKTREE}")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or client.user is None:
        return
    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    member_roles: set[int] = set()
    if isinstance(message.author, discord.Member):
        member_roles = {r.id for r in message.author.roles}
    if not is_authorized(message.author.id, member_roles, ALLOWED_USER_IDS, ALLOWED_ROLE_IDS):
        return

    raw = message.content.strip()
    if not raw and not message.attachments:
        return

    verdict = check_prompt_injection(raw)
    if not verdict.allowed:
        await message.reply(
            f"refused: {verdict.reason}\nmatched: `{verdict.matched_pattern}`",
            mention_author=False,
        )
        return

    async with message.channel.typing():
        try:
            staged = await _stage_attachments(message)
        except Exception as e:  # noqa: BLE001
            await message.reply(f"could not stage attachments: {e}", mention_author=False)
            return

        result = await _run_agent(raw, staged)

    prefix = "ok" if result.get("ok") else "fail"
    body = result.get("summary", "(no summary)")
    out = f"[{prefix}] {body}"
    for chunk in _chunk_for_discord(out):
        await message.channel.send(chunk)


def main() -> None:
    _fatal_config_check()
    client.run(os.environ["DISCORD_BOT_TOKEN"])


if __name__ == "__main__":
    main()
