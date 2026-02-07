"""
Echo — Mocking Message Repetition Commands

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

Commands in this module:
- echo {user}: Apply Echo to a user
- unecho {user}: Remove Echo from a user

Behavior:
- Replies to user messages by reposting the original message with exaggerated casing
- Adds randomized mocking commentary and emojis
- May also trigger media responses via the media system

This module weaponizes user speech without blocking it.
All commands are registered explicitly via `register(bot)`.
"""

from __future__ import annotations

from typing import Optional
import random

import discord
from discord.ext import commands

from locks import honkify
from state import memory
from utils.text import mock_case, normalize_whitespace, safe_truncate

WEBHOOK_NAME = "EchoLock"
MAX_REPLY_LENGTH = 1900

_COMMENTARY = [
    "wow okay",
    "listen to yourself",
    "bold thing to say",
    "that’s what you sound like",
    "real original",
    "sure thing",
]

_EMOJIS = ["🙄", "😬", "🤡", "😂", "😒", "🪿"]


def _format_lock_status(member: discord.Member) -> str:
    if not memory.is_echolocked(member.id):
        return f"{member.display_name} is not echolocked."
    locked_at = memory.get_echolock_time(member.id)
    if locked_at is None:
        return f"{member.display_name} is echolocked."
    return f"{member.display_name} is echolocked (since <t:{int(locked_at)}:R>)."


def _build_echo_reply(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""
    mocked = mock_case(cleaned, start_upper=random.choice([True, False]))
    commentary = random.choice(_COMMENTARY)
    emoji = random.choice(_EMOJIS)
    return f"{mocked}\n*{commentary}* {emoji}"


async def _resolve_member(ctx: commands.Context, target: str) -> Optional[discord.Member]:
    try:
        return await commands.MemberConverter().convert(ctx, target)
    except commands.BadArgument:
        return None


async def _get_or_create_webhook(channel: discord.TextChannel) -> Optional[discord.Webhook]:
    try:
        webhooks = await channel.webhooks()
        existing = next((hook for hook in webhooks if hook.name == WEBHOOK_NAME), None)
        if existing:
            return existing
        return await channel.create_webhook(name=WEBHOOK_NAME)
    except (discord.Forbidden, discord.HTTPException):
        return None


async def _emit_echo(message: discord.Message, content: str) -> None:
    webhook = None
    if isinstance(message.channel, discord.TextChannel):
        webhook = await _get_or_create_webhook(message.channel)

    if webhook:
        await webhook.send(
            content,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    else:
        await message.channel.send(content, allowed_mentions=discord.AllowedMentions.none())

    try:
        await message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass


def register(bot: commands.Bot) -> None:
    @bot.command(name="echo")
    @commands.has_permissions(administrator=True)
    async def echo_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        if not target:
            await ctx.reply("Specify a user or `all`.")
            return

        if target.lower() == "all":
            if not ctx.guild:
                await ctx.reply("This command requires a server context.")
                return
            count = 0
            for member in ctx.guild.members:
                if member.bot:
                    continue
                if not memory.is_echolocked(member.id):
                    memory.set_echolock(member.id)
                    count += 1
            await ctx.reply(f"Echolocked {count} users.")
            return

        member = await _resolve_member(ctx, target)
        if not member:
            await ctx.reply("Could not resolve that user.")
            return
        if memory.is_echolocked(member.id):
            await ctx.reply(f"{member.display_name} is already echolocked.")
            return
        memory.set_echolock(member.id)
        await ctx.reply(f"{member.display_name} is now echolocked.")

    @bot.command(name="unecho")
    @commands.has_permissions(administrator=True)
    async def unecho_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        if not target:
            await ctx.reply("Specify a user or `all`.")
            return

        if target.lower() == "all":
            memory.reset_all_echolocks()
            await ctx.reply("All echolocks removed.")
            return

        member = await _resolve_member(ctx, target)
        if not member:
            await ctx.reply("Could not resolve that user.")
            return
        if not memory.is_echolocked(member.id):
            await ctx.reply(f"{member.display_name} is not echolocked.")
            return
        memory.clear_echolock(member.id)
        await ctx.reply(f"{member.display_name} has been unechoed.")

    @bot.command(name="echo?")
    async def echo_status_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        if not target:
            await ctx.reply(_format_lock_status(ctx.author))
            return
        if target.lower() == "all":
            locked = memory.get_all_echolocks()
            if not locked:
                await ctx.reply("No users are echolocked.")
                return
            mentions = ", ".join(f"<@{user_id}>" for user_id in locked.keys())
            await ctx.reply(f"Echolocked users: {mentions}")
            return
        member = await _resolve_member(ctx, target)
        if not member:
            await ctx.reply("Could not resolve that user.")
            return
        await ctx.reply(_format_lock_status(member))

    @bot.listen("on_message")
    async def echolock_listener(message: discord.Message) -> None:
        if honkify._should_ignore_message(message, bot):
            return
        if not message.content:
            return
        if not memory.is_echolocked(message.author.id):
            return

        reply = _build_echo_reply(message.content)
        if not reply:
            return

        reply = safe_truncate(reply, MAX_REPLY_LENGTH)
        await _emit_echo(message, reply)
