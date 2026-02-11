"""
Media Actions — Media-Based Commands and Autonomous Responses

THIS MODULE DEFINES USER COMMANDS AND AUTONOMOUS TRIGGERS.

Commands:
- Manual goose media posts
- Context-based media replies

Autonomous behavior:
- Retaliatory gifs/images
- Random contextual interruptions
- DM-based image delivery

This module executes media actions and exposes `register(bot)`.
"""

from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import discord
from discord.ext import commands

from media.context import context_analyzer
from media.providers import MediaItem, MediaProviderHub
from state import memory
from utils.text import normalize_whitespace, tokenize

COOLDOWN_KEY = "media_autonomous"
DEFAULT_AUTONOMOUS_COOLDOWN_SECONDS = 120.0
DEFAULT_AUTONOMOUS_CHANCE = 0.035
DEFAULT_RETALIATION_CHANCE = 0.12
DEFAULT_DM_CHANCE = 0.12
DEFAULT_GUILD_WIDE_DM_CHANCE = 0.15
MAX_CONTEXT_KEYWORDS = 6
MIN_KEYWORD_LENGTH = 3

_RETALIATION_TOKENS = {"honk", "goose", "attack", "bite", "mean", "rage"}

_media_hub = MediaProviderHub()
_media_initialized = False
_media_init_lock = asyncio.Lock()


async def _ensure_media_initialized() -> None:
    global _media_initialized
    if _media_initialized:
        return
    async with _media_init_lock:
        if _media_initialized:
            return
        await _media_hub.initialize()
        _media_initialized = True


def _should_ignore_message(message: discord.Message, bot: commands.Bot) -> bool:
    if message.author.bot:
        return True
    prefix = bot.command_prefix
    if isinstance(prefix, str) and message.content.startswith(prefix):
        return True
    return False


def _keywords_from_text(text: str) -> List[str]:
    cleaned = normalize_whitespace(text or "")
    if not cleaned:
        return []
    keywords = []
    for token in tokenize(cleaned):
        lowered = token.lower()
        if len(lowered) < MIN_KEYWORD_LENGTH or not lowered.isalnum():
            continue
        keywords.append(lowered)
    return keywords


def _build_context_for_message(message: discord.Message) -> Dict[str, object]:
    snapshot = context_analyzer.summarize_context()
    top_keywords = [word for word, _ in snapshot.top_keywords[:MAX_CONTEXT_KEYWORDS]]
    inferred_topics = [topic for topic, _ in snapshot.inferred_topics]
    keywords = top_keywords[:]
    keywords.extend(inferred_topics)

    channel_id = message.channel.id
    honk_count = memory.get_channel_honk_activity(channel_id)
    threshold = memory.get_takeover_threshold(channel_id)
    honk_density = honk_count / max(1, threshold)

    return {
        "guild_id": message.guild.id if message.guild else None,
        "channel_id": channel_id,
        "keywords": keywords,
        "topics": inferred_topics,
        "honk_density": honk_density,
    }


def _context_query_from_snapshot() -> Optional[str]:
    snapshot = context_analyzer.summarize_context()
    if not snapshot.top_keywords:
        return None
    top_keywords = [word for word, _ in snapshot.top_keywords[:MAX_CONTEXT_KEYWORDS]]
    return " ".join(top_keywords) if top_keywords else None


async def _send_media(
    destination: discord.abc.Messageable,
    item: MediaItem,
    *,
    preface: Optional[str] = None,
) -> None:
    if not item:
        return
    message = preface or ""
    item_type = item.get("type")
    value = item.get("value")

    if item_type == "file":
        path = Path(str(value))
        if not path.exists():
            return
        file = discord.File(path)
        if message:
            await destination.send(message, file=file)
        else:
            await destination.send(file=file)
        return

    if item_type == "url" and value:
        if message:
            await destination.send(f"{message}\n{value}")
        else:
            await destination.send(str(value))


async def _post_media(
    destination: discord.abc.Messageable,
    *,
    query: Optional[str],
    context: Dict[str, object],
) -> bool:
    await _ensure_media_initialized()
    if query:
        item = await _media_hub.search(query, context)
    else:
        item = await _media_hub.get_random(context)
    if not item:
        return False
    await _send_media(destination, item)
    return True


def _is_on_cooldown(channel_id: int) -> bool:
    return memory.is_on_cooldown(COOLDOWN_KEY, channel_id)


def _trigger_cooldown(channel_id: int, *, seconds: float) -> None:
    memory.set_cooldown(COOLDOWN_KEY, channel_id, time.time() + seconds)


def _should_retaliate(message: discord.Message) -> bool:
    tokens = {token.lower() for token in tokenize(message.content or "")}
    if tokens.intersection(_RETALIATION_TOKENS):
        return True
    if random.random() < DEFAULT_RETALIATION_CHANCE:
        return True
    return False


def _choose_dm_target(
    message: discord.Message,
    *,
    allow_guild_wide: bool,
) -> Optional[discord.Member]:
    if not message.guild:
        return None

    channel_members = [
        member for member in message.channel.members if not member.bot
    ] if isinstance(message.channel, discord.TextChannel) else []
    guild_members = [member for member in message.guild.members if not member.bot]

    if allow_guild_wide and random.random() < DEFAULT_GUILD_WIDE_DM_CHANCE and guild_members:
        return random.choice(guild_members)
    if channel_members:
        return random.choice(channel_members)
    if guild_members:
        return random.choice(guild_members)
    return None


async def _maybe_send_dm_media(message: discord.Message, context: Dict[str, object]) -> None:
    if random.random() > DEFAULT_DM_CHANCE:
        return
    target = _choose_dm_target(message, allow_guild_wide=True)
    if not target:
        return
    await _ensure_media_initialized()
    item = await _media_hub.get_random(context)
    if not item:
        return
    try:
        await _send_media(target, item, preface="🪿")
    except (discord.Forbidden, discord.HTTPException):
        return


async def _handle_autonomous_media(message: discord.Message) -> None:
    if not isinstance(message.channel, discord.TextChannel):
        return
    if _is_on_cooldown(message.channel.id):
        return
    if random.random() > DEFAULT_AUTONOMOUS_CHANCE:
        return

    context = _build_context_for_message(message)
    if _should_retaliate(message):
        context.setdefault("preferred_categories", ["angry", "chaos"])

    posted = await _post_media(message.channel, query=None, context=context)
    if posted:
        _trigger_cooldown(message.channel.id, seconds=DEFAULT_AUTONOMOUS_COOLDOWN_SECONDS)
    await _maybe_send_dm_media(message, context)


async def _index_server_media(message: discord.Message) -> None:
    if not message.guild or not message.attachments:
        return
    urls = [attachment.url for attachment in message.attachments if attachment.url]
    if not urls:
        return
    keywords = _keywords_from_text(message.content)
    if not keywords:
        keywords = ["goose"]
    _media_hub.add_server_media(message.guild.id, keywords, urls)


def register(bot: commands.Bot) -> None:
    @bot.command(name="goose")
    async def goose_cmd(ctx: commands.Context, *, query: Optional[str] = None) -> None:
        await _ensure_media_initialized()
        context = _build_context_for_message(ctx.message)
        success = await _post_media(ctx, query=query, context=context)
        if not success:
            await ctx.reply("No goose media found.", mention_author=False)

    @bot.command(name="goosecontext")
    async def goose_context_cmd(ctx: commands.Context) -> None:
        await _ensure_media_initialized()
        query = _context_query_from_snapshot()
        context = _build_context_for_message(ctx.message)
        success = await _post_media(ctx, query=query, context=context)
        if not success:
            await ctx.reply("No context media found.", mention_author=False)

    @bot.listen("on_message")
    async def media_listener(message: discord.Message) -> None:
        if _should_ignore_message(message, bot):
            return
        if message.content:
            context_analyzer.add_message(
                author=str(message.author.id),
                content=message.content,
            )
        await _index_server_media(message)
        await _handle_autonomous_media(message)
