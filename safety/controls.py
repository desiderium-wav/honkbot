"""
Safety Controls — Administrative Command Suite and Enforcement

THIS MODULE DEFINES SERVER OWNER/BOT OWNER-ONLY COMMANDS.

Commands:
- Enable/disable HonkBot per server
- Enable/disable specific systems
- Set channel exclusions
- Assign immunity roles
- Adjust rate limits

This module also enforces safety checks used by all systems.
A global owner-only override is supported.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Optional, Union

import discord
from discord.ext import commands

from state import memory

HONKBLOCK_ROLE_NAME = "honkblock"

SYSTEM_TOGGLES = (
    "chaos",
    "honkify",
    "honklock",
    "media",
    "voice",
    "retaliation",
    "mass_mentions",
)


GuildLike = Union[int, discord.Guild]
ChannelLike = Union[int, discord.abc.GuildChannel]


def _resolve_guild_id(guild: GuildLike) -> int:
    if isinstance(guild, discord.Guild):
        return guild.id
    return int(guild)


def _resolve_channel_id(channel: ChannelLike) -> int:
    if isinstance(channel, discord.abc.GuildChannel):
        return channel.id
    return int(channel)


def _get_owner_id() -> Optional[int]:
    raw = os.getenv("HONKBOT_OWNER_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_bot_owner(user_id: int) -> bool:
    owner_id = _get_owner_id()
    return owner_id is not None and user_id == owner_id


def _has_guild_control(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return False
    if _is_bot_owner(ctx.author.id):
        return True
    if ctx.guild.owner_id == ctx.author.id:
        return True
    return bool(getattr(ctx.author, "guild_permissions", None).administrator)


def get_guild_state(guild: GuildLike) -> Dict[str, object]:
    return memory.get_safety_state(_resolve_guild_id(guild))


def is_global_enabled() -> bool:
    return memory.get_global_safety_enabled()


def set_global_enabled(enabled: bool, *, actor_id: Optional[int] = None) -> bool:
    owner_id = _get_owner_id()
    if owner_id is None or actor_id != owner_id:
        return False
    memory.set_global_safety_enabled(bool(enabled))
    return True


def is_guild_enabled(guild: GuildLike) -> bool:
    state = get_guild_state(guild)
    return bool(state.get("enabled", True))


def set_guild_enabled(guild: GuildLike, enabled: bool) -> None:
    state = get_guild_state(guild)
    state["enabled"] = bool(enabled)


def is_enabled(guild: Optional[GuildLike] = None) -> bool:
    if not is_global_enabled():
        return False
    if guild is None:
        return True
    return is_guild_enabled(guild)


def is_module_enabled(guild: GuildLike, module: str) -> bool:
    if module not in SYSTEM_TOGGLES:
        return True
    state = get_guild_state(guild)
    toggles = state.get("module_toggles", {})
    return bool(toggles.get(module, True))


def is_system_enabled(guild: GuildLike, module: str) -> bool:
    return is_module_enabled(guild, module)


def set_module_enabled(guild: GuildLike, module: str, enabled: bool) -> bool:
    if module not in SYSTEM_TOGGLES:
        return False
    state = get_guild_state(guild)
    toggles = state.setdefault("module_toggles", {})
    toggles[module] = bool(enabled)
    return True


def get_module_toggles(guild: GuildLike) -> Dict[str, bool]:
    state = get_guild_state(guild)
    toggles = state.get("module_toggles", {})
    return {module: bool(toggles.get(module, True)) for module in SYSTEM_TOGGLES}


def is_channel_allowed(guild: GuildLike, channel: ChannelLike) -> bool:
    state = get_guild_state(guild)
    exclusions = state.get("channel_exclusions", set())
    return _resolve_channel_id(channel) not in exclusions


def is_channel_enabled(guild: GuildLike, channel: ChannelLike) -> bool:
    return is_channel_allowed(guild, channel)


def channel_allowed(guild: GuildLike, channel: ChannelLike) -> bool:
    return is_channel_allowed(guild, channel)


def add_channel_exclusion(guild: GuildLike, channel: ChannelLike) -> None:
    state = get_guild_state(guild)
    exclusions = state.setdefault("channel_exclusions", set())
    exclusions.add(_resolve_channel_id(channel))


def remove_channel_exclusion(guild: GuildLike, channel: ChannelLike) -> None:
    state = get_guild_state(guild)
    exclusions = state.setdefault("channel_exclusions", set())
    exclusions.discard(_resolve_channel_id(channel))


def clear_channel_exclusions(guild: GuildLike) -> None:
    state = get_guild_state(guild)
    exclusions = state.setdefault("channel_exclusions", set())
    exclusions.clear()


def _cooldown_key(key: str, channel_id: Optional[int] = None) -> str:
    if channel_id is None:
        return f"guild:{key}"
    return f"channel:{channel_id}:{key}"


def set_cooldown(
    guild: GuildLike,
    key: str,
    cooldown_seconds: float,
    *,
    channel: Optional[ChannelLike] = None,
) -> float:
    state = get_guild_state(guild)
    cooldowns = state.setdefault("cooldowns", {})
    now = time.monotonic()
    until = now + max(0.0, cooldown_seconds)
    channel_id = _resolve_channel_id(channel) if channel is not None else None
    cooldowns[_cooldown_key(key, channel_id)] = until
    return until


def clear_cooldown(
    guild: GuildLike,
    key: str,
    *,
    channel: Optional[ChannelLike] = None,
) -> None:
    state = get_guild_state(guild)
    cooldowns = state.setdefault("cooldowns", {})
    channel_id = _resolve_channel_id(channel) if channel is not None else None
    cooldowns.pop(_cooldown_key(key, channel_id), None)


def cooldown_active(
    guild: GuildLike,
    key: str,
    *,
    channel: Optional[ChannelLike] = None,
    now: Optional[float] = None,
) -> bool:
    state = get_guild_state(guild)
    cooldowns = state.setdefault("cooldowns", {})
    channel_id = _resolve_channel_id(channel) if channel is not None else None
    timestamp = cooldowns.get(_cooldown_key(key, channel_id))
    if timestamp is None:
        return False
    current = time.monotonic() if now is None else now
    return current < float(timestamp)


def cooldown_remaining(
    guild: GuildLike,
    key: str,
    *,
    channel: Optional[ChannelLike] = None,
    now: Optional[float] = None,
) -> float:
    state = get_guild_state(guild)
    cooldowns = state.setdefault("cooldowns", {})
    channel_id = _resolve_channel_id(channel) if channel is not None else None
    timestamp = cooldowns.get(_cooldown_key(key, channel_id))
    if timestamp is None:
        return 0.0
    current = time.monotonic() if now is None else now
    return max(0.0, float(timestamp) - current)


async def ensure_honkblock_role(guild: discord.Guild) -> Optional[discord.Role]:
    for role in guild.roles:
        if role.name == HONKBLOCK_ROLE_NAME:
            return role
    try:
        return await guild.create_role(
            name=HONKBLOCK_ROLE_NAME,
            reason="HonkBot safety immunity role",
        )
    except Exception:
        return None


def user_has_immunity(member: Optional[discord.Member]) -> bool:
    if member is None:
        return False
    roles = getattr(member, "roles", None)
    if not roles:
        return False
    return any(role.name == HONKBLOCK_ROLE_NAME for role in roles)


def safety_allows(
    *,
    guild: GuildLike,
    channel: Optional[ChannelLike] = None,
    member: Optional[discord.Member] = None,
    module: Optional[str] = None,
) -> bool:
    if not is_enabled(guild):
        return False
    if module and not is_module_enabled(guild, module):
        return False
    if channel and not is_channel_allowed(guild, channel):
        return False
    if member and user_has_immunity(member):
        return False
    return True


def register(bot: commands.Bot) -> None:
    @bot.group(name="safety", invoke_without_command=True)
    @commands.check(_has_guild_control)
    async def safety_group(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        toggles = get_module_toggles(ctx.guild)
        exclusions = get_guild_state(ctx.guild).get("channel_exclusions", set())
        status_lines = [
            f"Global enabled: {'on' if is_global_enabled() else 'off'}",
            f"Guild enabled: {'on' if is_guild_enabled(ctx.guild) else 'off'}",
            f"Excluded channels: {len(exclusions)}",
            "Module toggles:",
        ]
        for module in SYSTEM_TOGGLES:
            status_lines.append(f"- {module}: {'on' if toggles.get(module, True) else 'off'}")
        await ctx.reply("\n".join(status_lines))

    @safety_group.command(name="enable")
    @commands.check(_has_guild_control)
    async def safety_enable(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        set_guild_enabled(ctx.guild, True)
        await ctx.reply("Safety enabled for this server.")

    @safety_group.command(name="disable")
    @commands.check(_has_guild_control)
    async def safety_disable(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        set_guild_enabled(ctx.guild, False)
        await ctx.reply("Safety disabled for this server.")

    @safety_group.command(name="global")
    async def safety_global(ctx: commands.Context, flag: str) -> None:
        if not _is_bot_owner(ctx.author.id):
            await ctx.reply("Only the bot owner can change global safety.")
            return
        enabled = flag.lower() in {"on", "enable", "enabled", "true", "1"}
        if not set_global_enabled(enabled, actor_id=ctx.author.id):
            await ctx.reply("Failed to update global safety.")
            return
        await ctx.reply(f"Global safety {'enabled' if enabled else 'disabled'}.")

    @safety_group.command(name="module")
    @commands.check(_has_guild_control)
    async def safety_module(ctx: commands.Context, module: str, flag: str) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        module_key = module.lower()
        if module_key not in SYSTEM_TOGGLES:
            await ctx.reply(f"Unknown module. Valid: {', '.join(SYSTEM_TOGGLES)}")
            return
        enabled = flag.lower() in {"on", "enable", "enabled", "true", "1"}
        set_module_enabled(ctx.guild, module_key, enabled)
        await ctx.reply(f"Module {module_key} {'enabled' if enabled else 'disabled'}.")

    @safety_group.group(name="exclude", invoke_without_command=True)
    @commands.check(_has_guild_control)
    async def safety_exclude(ctx: commands.Context) -> None:
        await ctx.reply("Usage: safety exclude add|remove|clear")

    @safety_exclude.command(name="add")
    @commands.check(_has_guild_control)
    async def safety_exclude_add(ctx: commands.Context, channel: discord.TextChannel) -> None:
        add_channel_exclusion(ctx.guild, channel)
        await ctx.reply(f"Excluded {channel.mention} from chaos actions.")

    @safety_exclude.command(name="remove")
    @commands.check(_has_guild_control)
    async def safety_exclude_remove(ctx: commands.Context, channel: discord.TextChannel) -> None:
        remove_channel_exclusion(ctx.guild, channel)
        await ctx.reply(f"Removed {channel.mention} from exclusions.")

    @safety_exclude.command(name="clear")
    @commands.check(_has_guild_control)
    async def safety_exclude_clear(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        clear_channel_exclusions(ctx.guild)
        await ctx.reply("Cleared all channel exclusions.")

    @safety_group.group(name="cooldown", invoke_without_command=True)
    @commands.check(_has_guild_control)
    async def safety_cooldown(ctx: commands.Context) -> None:
        await ctx.reply("Usage: safety cooldown set|clear <key> [seconds] [#channel]")

    @safety_cooldown.command(name="set")
    @commands.check(_has_guild_control)
    async def safety_cooldown_set(
        ctx: commands.Context,
        key: str,
        seconds: float,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        until = set_cooldown(ctx.guild, key, seconds, channel=channel)
        remaining = max(0.0, until - time.monotonic())
        if channel:
            await ctx.reply(f"Cooldown set for {key} in {channel.mention} ({remaining:.1f}s).")
        else:
            await ctx.reply(f"Cooldown set for {key} in this server ({remaining:.1f}s).")

    @safety_cooldown.command(name="clear")
    @commands.check(_has_guild_control)
    async def safety_cooldown_clear(
        ctx: commands.Context,
        key: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        clear_cooldown(ctx.guild, key, channel=channel)
        if channel:
            await ctx.reply(f"Cooldown cleared for {key} in {channel.mention}.")
        else:
            await ctx.reply(f"Cooldown cleared for {key} in this server.")
