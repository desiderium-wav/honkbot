"""
Echo — Mocking Message Repetition Commands (hybrid-friendly)

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

Commands in this module:
- echo {member} [all_users]: Apply Echo to a user or everyone
- unecho {member} [all_users]: Remove Echo from a user or everyone
- echo_status {member} [all_users]: Query Echo status (slash-friendly)
- echo? (legacy prefix-only alias) — preserved for backwards compatibility

Behavior:
- Replies to user messages by reposting the original message with exaggerated casing
- Adds randomized mocking commentary and emojis
- May also trigger media responses via the media system

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
    @commands.hybrid_command(name="echo")
    @commands.has_permissions(administrator=True)
    async def echo_cmd(
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        all_users: bool = False,
    ) -> None:
        """Echolock a member, or all members with the all_users flag."""
        if all_users:
            if not ctx.guild:
                await ctx.reply("This command requires a server context.")
                return
            count = 0
            for m in ctx.guild.members:
                if m.bot:
                    continue
                if not memory.is_echolocked(m.id):
                    memory.set_echolock(m.id)
                    count += 1
            await ctx.reply(f"Echolocked {count} users.")
            return

        if member is None:
            await ctx.reply("Specify a user or use the `all_users` flag.")
            return

        if memory.is_echolocked(member.id):
            await ctx.reply(f"{member.display_name} is already echolocked.")
            return
        memory.set_echolock(member.id)
        await ctx.reply(f"{member.display_name} is now echolocked.")

    @commands.hybrid_command(name="unecho")
    @commands.has_permissions(administrator=True)
    async def unecho_cmd(
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        all_users: bool = False,
    ) -> None:
        """Remove echolock from a member or all members."""
        if all_users:
            memory.reset_all_echolocks()
            await ctx.reply("All echolocks removed.")
            return

        if member is None:
            await ctx.reply("Specify a user or use the `all_users` flag.")
            return

        if not memory.is_echolocked(member.id):
            await ctx.reply(f"{member.display_name} is not echolocked.")
            return
        memory.clear_echolock(member.id)
        await ctx.reply(f"{member.display_name} has been unechoed.")

    # Slash-friendly hybrid status command
    @commands.hybrid_command(name="echo_status")
    async def echo_status_cmd(
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        all_users: bool = False,
    ) -> None:
        """Query echolock status for a member or list all echolocked users."""
        if all_users:
            locked = memory.get_all_echolocks()
            if not locked:
                await ctx.reply("No users are echolocked.")
                return
            mentions = ", ".join(f"<@{user_id}>" for user_id in locked.keys())
            await ctx.reply(f"Echolocked users: {mentions}")
            return

        target = member or ctx.author
        await ctx.reply(_format_lock_status(target))

    # Legacy prefix-only alias to preserve the original "echo?" command name.
    # Keep the prefix alias for backward compatibility, but invoke the existing
    # echo_status hybrid command so the slash version is the canonical implementation.
    @bot.command(name="echo?")
    async def echo_question_alias(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        """Legacy prefix-only alias for echo status (keeps `echo?` working).
        Invokes the /echo_status implementation under the hood.
        """
        all_users = False
        member_obj: Optional[discord.Member] = None

        if not target:
            member_obj = None
        elif target.lower() == "all":
            all_users = True
        else:
            member_obj = await _resolve_member(ctx, target)
            if member_obj is None:
                await ctx.reply("Could not resolve that user.")
                return

        cmd = ctx.bot.get_command("echo_status")
        if cmd is None:
            target_member = member_obj or ctx.author
            await ctx.reply(_format_lock_status(target_member))
            return

        await ctx.invoke(cmd, member=member_obj, all_users=all_users)

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
