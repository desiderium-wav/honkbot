"""
HonkLock — Persistent Goose-Themed Message Lock

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

HonkLock enforces persistent honkification on a user.
Once locked, ALL of the user’s messages are honkified
until unlocked by an admin or the bot itself

Responsibilities:
- Apply and remove honklocks on users
- Intercept messages from locked users and send the honkified version via webhook
- Delegate actual message transformation to Honkify
- Track lock duration and escalation potential

Commands in this module:
- honk {user}: Apply HonkLock to a user
- unhonk {user}: Remove HonkLock from a user
- honk all: Apply HonkLock to all users (administrators only)
- unhonk all: Remove HonkLock from all users (administrator only)
- honk? {user}: Query HonkLock status

IMPORTANT:
- This module does NOT define honk replacement logic.
- It relies entirely on Honkify for message transformation

Registered explicitly via `register(bot)`.
"""

from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from locks import honkify
from state import memory
from utils.text import safe_truncate

WEBHOOK_NAME = "HonkLock"
MAX_REPLY_LENGTH = 1900


def _format_lock_status(member: discord.Member) -> str:
    if not memory.is_honklocked(member.id):
        return f"{member.display_name} is not honklocked."
    locked_at = memory.get_honklock_time(member.id)
    if locked_at is None:
        return f"{member.display_name} is honklocked."
    return f"{member.display_name} is honklocked (since <t:{int(locked_at)}:R>)."


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


async def _emit_honkified(message: discord.Message, content: str) -> None:
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
    @bot.command(name="honk")
    @commands.has_permissions(administrator=True)
    async def honk_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
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
                if not memory.is_honklocked(member.id):
                    memory.set_honklock(member.id)
                    count += 1
            await ctx.reply(f"Honklocked {count} users.")
            return

        member = await _resolve_member(ctx, target)
        if not member:
            await ctx.reply("Could not resolve that user.")
            return
        if memory.is_honklocked(member.id):
            await ctx.reply(f"{member.display_name} is already honklocked.")
            return
        memory.set_honklock(member.id)
        await ctx.reply(f"{member.display_name} is now honklocked.")

    @bot.command(name="unhonk")
    @commands.has_permissions(administrator=True)
    async def unhonk_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        if not target:
            await ctx.reply("Specify a user or `all`.")
            return

        if target.lower() == "all":
            memory.reset_all_honklocks()
            await ctx.reply("All honklocks removed.")
            return

        member = await _resolve_member(ctx, target)
        if not member:
            await ctx.reply("Could not resolve that user.")
            return
        if not memory.is_honklocked(member.id):
            await ctx.reply(f"{member.display_name} is not honklocked.")
            return
        memory.clear_honklock(member.id)
        await ctx.reply(f"{member.display_name} has been unhonked.")

    @bot.command(name="honk?")
    async def honk_status_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        if not target:
            await ctx.reply(_format_lock_status(ctx.author))
            return
        if target.lower() == "all":
            locked = memory.get_all_honklocks()
            if not locked:
                await ctx.reply("No users are honklocked.")
                return
            mentions = ", ".join(f"<@{user_id}>" for user_id in locked.keys())
            await ctx.reply(f"Honklocked users: {mentions}")
            return
        member = await _resolve_member(ctx, target)
        if not member:
            await ctx.reply("Could not resolve that user.")
            return
        await ctx.reply(_format_lock_status(member))

    @bot.listen("on_message")
    async def honklock_listener(message: discord.Message) -> None:
        if honkify._should_ignore_message(message, bot):
            return
        if not message.content:
            return
        if not memory.is_honklocked(message.author.id):
            return

        outcome = honkify.honkify_message(
            message.content,
            user_id=message.author.id,
            channel_id=message.channel.id,
            force=True,
        )
        if not outcome or not outcome.honkified_text:
            return

        reply = safe_truncate(outcome.honkified_text, MAX_REPLY_LENGTH)
        await _emit_honkified(message, reply)
