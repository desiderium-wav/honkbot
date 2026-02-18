"""
Honkify — Core Honk Message Transformation System (hybrid commands)

THIS MODULE DEFINES USER COMMANDS, AUTONOMOUS TRIGGERS, AND CORE LOGIC.

Honkify is the primitive honk transformation system.
It applies honk-based message replacement WITHOUT locking the user.

Responsibilities:
- Transform a single message by replacing words with "honk"
- Detect existing "honk" usage and amplify behavior
- Increment per-user honk counters
- Trigger special responses:
  - Lone honk reply (single-word "honk")
  - Double honk amplification (messages already containing honk)
- Serve as a random chaos event
- Support manual admin-triggered honkify via message reply OR slash-native message reference (link or id)
- Feed honk counts into escalation systems (takeovers, retaliation)

IMPORTANT DISTINCTION:
- Honkify is stateless and per-message.
- HonkLock enforces persistent honkification and calls Honkify internally.

Commands defined here:
- honkify: Honkify a message (admin-only). Supports:
    * reply-based (no options) — existing behavior
    * slash/native: message_link (str) OR message_id (int) with optional channel (TextChannel)
- honkstats {user}: Show per user honk stats (if no user is defined, the bot will show personal stats for the user sending the command)
- tophonk: Show honk leaderboard

This module exposes `register(bot)` for command registration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import random
import re

import discord
from discord.ext import commands

from state import memory
from utils.text import normalize_whitespace, safe_truncate

HONK_WORD = "honk"
HONK_REGEX = re.compile(r"\bhonk\b", re.IGNORECASE)

DEFAULT_HONKIFY_CHANCE = 0.12
DEFAULT_DOUBLE_HONK_CHANCE = 0.65
MAX_REPLY_LENGTH = 1900

# Regex to parse discord message links:
_MESSAGE_LINK_RE = re.compile(
    r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/"
    r"(?P<guild_id>\d+)/(?P<channel_id>\d+)/(?P<message_id>\d+)"
)


@dataclass(frozen=True)
class HonkifyOutcome:
    honkified_text: Optional[str]
    action: str
    honk_delta: int
    channel_delta: int
    lone_honk: bool
    double_honk: bool
    takeover_ready: bool


def _word_honkify(text: str, *, honk: str = HONK_WORD) -> str:
    if not text:
        return text
    return re.sub(r"\b[\w']+\b", honk, text)


def _is_lone_honk(text: str) -> bool:
    return normalize_whitespace(text).lower() == HONK_WORD


def _count_honks(text: str) -> int:
    return len(HONK_REGEX.findall(text))


def _amplify_honk(text: str, *, honk: str = HONK_WORD) -> str:
    upper = honk.upper()
    return f"{upper} {upper}!"


def _update_honk_counts(user_id: int, channel_id: int, amount: int) -> tuple[int, int, bool]:
    user_count = memory.increment_user_honk_count(user_id, amount)
    channel_count = memory.increment_channel_honk_activity(channel_id, amount)
    takeover_ready = memory.is_takeover_ready(channel_id, channel_count)
    return user_count, channel_count, takeover_ready


def honkify_message(
    text: str,
    *,
    user_id: int,
    channel_id: int,
    force: bool = False,
    chaos_chance: float = DEFAULT_HONKIFY_CHANCE,
    double_honk_chance: float = DEFAULT_DOUBLE_HONK_CHANCE,
) -> Optional[HonkifyOutcome]:
    if not text:
        return None

    honk_count = _count_honks(text)
    lone_honk = _is_lone_honk(text)
    has_honk = honk_count > 0

    should_honkify = force or (random.random() < chaos_chance) or has_honk
    if not should_honkify:
        return None

    if lone_honk:
        _, _, takeover_ready = _update_honk_counts(user_id, channel_id, 1)
        return HonkifyOutcome(
            honkified_text=HONK_WORD,
            action="lone_honk_reply",
            honk_delta=1,
            channel_delta=1,
            lone_honk=True,
            double_honk=False,
            takeover_ready=takeover_ready,
        )

    if has_honk and random.random() < double_honk_chance:
        _, _, takeover_ready = _update_honk_counts(user_id, channel_id, 2)
        return HonkifyOutcome(
            honkified_text=_amplify_honk(text),
            action="double_honk_amplify",
            honk_delta=2,
            channel_delta=2,
            lone_honk=False,
            double_honk=True,
            takeover_ready=takeover_ready,
        )

    honkified = _word_honkify(text)
    _, _, takeover_ready = _update_honk_counts(user_id, channel_id, 1)
    return HonkifyOutcome(
        honkified_text=honkified,
        action="honkified",
        honk_delta=1,
        channel_delta=1,
        lone_honk=False,
        double_honk=False,
        takeover_ready=takeover_ready,
    )


def _format_leaderboard(user_ids: Sequence[int], *, guild: Optional[discord.Guild]) -> str:
    rows = []
    for rank, user_id in enumerate(user_ids, start=1):
        count = memory.get_user_honk_count(user_id)
        member = guild.get_member(user_id) if guild else None
        name = member.display_name if member else f"<@{user_id}>"
        rows.append(f"{rank}. {name} — {count} honks")
    return "\n".join(rows) if rows else "No honk stats yet."


async def _fetch_reply_message(ctx: commands.Context) -> Optional[discord.Message]:
    if not ctx.message or not ctx.message.reference or not ctx.message.reference.message_id:
        return None
    try:
        return await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def _fetch_message_from_link_or_id(
    ctx: commands.Context,
    *,
    message_link: Optional[str] = None,
    message_id: Optional[int] = None,
    channel: Optional[discord.TextChannel] = None,
) -> Optional[discord.Message]:
    """
    Resolve a message from:
      - message_link (discord message URL)
      - message_id (int) + optional channel
      - fallback to reply-based message reference
    """
    bot = ctx.bot

    if message_link:
        m = _MESSAGE_LINK_RE.search(message_link)
        if m:
            try:
                guild_id = int(m.group("guild_id"))
                channel_id = int(m.group("channel_id"))
                msg_id = int(m.group("message_id"))
            except Exception:
                return None
            # Prefer guild-local channel
            target_channel = None
            if ctx.guild and ctx.guild.id == guild_id:
                target_channel = ctx.guild.get_channel(channel_id)
            if target_channel is None:
                target_channel = bot.get_channel(channel_id)
            if isinstance(target_channel, discord.TextChannel):
                try:
                    return await target_channel.fetch_message(msg_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    return None
        return None

    if message_id is not None:
        # If channel provided, use it; else try current channel (if text) or try to look up via bot
        target_channel = None
        if channel is not None:
            target_channel = channel
        elif isinstance(ctx.channel, discord.TextChannel):
            target_channel = ctx.channel
        else:
            # try to find in guild if available
            if ctx.guild:
                # search through text channels might be expensive; prefer bot.get_channel if id encoded in message_id is unknown
                target_channel = None

        if isinstance(target_channel, discord.TextChannel):
            try:
                return await target_channel.fetch_message(int(message_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        # As a last resort, try fetching from current channel if possible
        if isinstance(ctx.channel, discord.TextChannel):
            try:
                return await ctx.channel.fetch_message(int(message_id))
            except Exception:
                return None

    # Fallback to reply-based behavior
    return await _fetch_reply_message(ctx)


def _should_ignore_message(message: discord.Message, bot: commands.Bot) -> bool:
    if message.author.bot:
        return True
    # Avoid honkifying command messages (best-effort).
    prefix = bot.command_prefix
    if isinstance(prefix, str) and message.content.startswith(prefix):
        return True
    return False


def register(bot: commands.Bot) -> None:
    @commands.hybrid_command(
        name="honkify",
        with_app_command=True,
        description="Honkify a message. If no options are given, honkify the replied-to message."
    )
    @commands.has_permissions(administrator=True)
    async def honkify_cmd(
        ctx: commands.Context,
        message_link: Optional[str] = None,
        message_id: Optional[int] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Admin command to force-honkify a specific message.

        Usage patterns:
        - reply-based (no opts): reply to a message and run the command (keeps original behavior)
        - slash-based: provide message_link OR message_id (and optional channel if needed)
        """

        target = await _fetch_message_from_link_or_id(
            ctx, message_link=message_link, message_id=message_id, channel=channel
        )

        if not target:
            await ctx.reply(
                "Could not resolve a target message. Reply to a message or provide a message link / message ID (with channel if necessary).",
                mention_author=False,
            )
            return

        outcome = honkify_message(
            target.content,
            user_id=target.author.id,
            channel_id=target.channel.id,
            force=True,
        )
        if not outcome or not outcome.honkified_text:
            await ctx.reply("Nothing to honkify.", mention_author=False)
            return
        reply = safe_truncate(outcome.honkified_text, MAX_REPLY_LENGTH)
        await ctx.reply(reply, mention_author=False)

    @commands.hybrid_command(name="honkstats")
    async def honkstats_cmd(ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Show honk stats for a member (or yourself)."""
        target = member or ctx.author
        count = memory.get_user_honk_count(target.id)
        await ctx.reply(f"{target.display_name} has {count} honks.", mention_author=False)

    @commands.hybrid_command(name="tophonk")
    async def tophonk_cmd(ctx: commands.Context) -> None:
        """Show the honk leaderboard."""
        user_ids = sorted(
            memory._user_honk_counts.keys(),
            key=lambda user_id: memory.get_user_honk_count(user_id),
            reverse=True,
        )
        leaderboard = _format_leaderboard(user_ids[:10], guild=ctx.guild)
        await ctx.reply(leaderboard, mention_author=False)

    @bot.listen("on_message")
    async def honkify_listener(message: discord.Message) -> None:
        if _should_ignore_message(message, bot):
            return
        if not message.content:
            return
        outcome = honkify_message(
            message.content,
            user_id=message.author.id,
            channel_id=message.channel.id,
        )
        if not outcome or not outcome.honkified_text:
            return
        reply = safe_truncate(outcome.honkified_text, MAX_REPLY_LENGTH)
        await message.reply(reply, mention_author=False)
