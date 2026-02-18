"""
Safety Controls — Administrative Command Suite and Enforcement

THIS MODULE DEFINES SERVER OWNER/BOT OWNER-ONLY COMMANDS.

Provides both:
- Prefix commands (legacy, accept string boolean flags like "on"/"off")
- Slash commands (typed options, better UX)

Permission model:
- Guild-level controls: guild owner, server administrators, or bot owner
- Global control: bot owner only
"""
from __future__ import annotations

import os
import time
from typing import Dict, Optional, Union

import discord
from discord.ext import commands
from discord import app_commands

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


def _has_guild_control_ctx(ctx: commands.Context) -> bool:
    """Check guild control for prefix command contexts."""
    if ctx.guild is None:
        return False
    if _is_bot_owner(ctx.author.id):
        return True
    if ctx.guild.owner_id == ctx.author.id:
        return True
    return bool(getattr(ctx.author, "guild_permissions", None).administrator)


def _has_guild_control_interaction(interaction: discord.Interaction) -> bool:
    """
    Check guild control for app command interactions WITHOUT awaiting.

    Important: avoid awaiting (e.g., fetch_member) here to prevent interaction timeouts.
    Use the interaction.user (Member) or guild cache.
    Returns False if permission cannot be determined quickly.
    """
    if interaction.guild is None:
        return False
    uid = interaction.user.id
    if _is_bot_owner(uid):
        return True
    if interaction.guild.owner_id == uid:
        return True

    # If interaction.user is a Member with guild_permissions, check that.
    user = interaction.user
    if isinstance(user, discord.Member) and getattr(user, "guild_permissions", None):
        return bool(user.guild_permissions.administrator)

    # Fall back to guild member cache (synchronous). Do NOT await fetch_member here.
    member = interaction.guild.get_member(uid)
    if member is not None:
        return bool(getattr(member, "guild_permissions", None).administrator)

    # Could not determine quickly; deny to avoid delays.
    return False


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


# --- Backward-compatible boolean parsing helper ---


def _parse_bool_flag(value) -> Optional[bool]:
    """
    Parse a boolean-like value (bool or string) into a bool.
    Returns None if unable to parse (caller can treat as error).
    Accepts common textual forms for prefix compatibility.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return bool(int(value))
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"on", "enable", "enabled", "true", "1", "yes", "y"}:
            return True
        if s in {"off", "disable", "disabled", "false", "0", "no", "n"}:
            return False
    return None


def register(bot: commands.Bot) -> None:
    # -----------------
    # Prefix (legacy) command group
    # -----------------
    @commands.group(name="safety", invoke_without_command=True)
    @commands.check(_has_guild_control_ctx)
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
    @commands.check(_has_guild_control_ctx)
    async def safety_enable(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        set_guild_enabled(ctx.guild, True)
        await ctx.reply("Safety enabled for this server.")

    @safety_group.command(name="disable")
    @commands.check(_has_guild_control_ctx)
    async def safety_disable(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        set_guild_enabled(ctx.guild, False)
        await ctx.reply("Safety disabled for this server.")

    @safety_group.command(name="global")
    async def safety_global(ctx: commands.Context, enabled: Optional[str] = None) -> None:
        """Prefix: Set global safety enabled/disabled. (bot owner only)

        Backward-compatible: accepts strings like "on"/"off" for prefix usage.
        """
        if not _is_bot_owner(ctx.author.id):
            await ctx.reply("Only the bot owner can change global safety.")
            return

        parsed = _parse_bool_flag(enabled)
        if parsed is None:
            await ctx.reply("Specify enabled as true/false or on/off.", mention_author=False)
            return

        if not set_global_enabled(parsed, actor_id=ctx.author.id):
            await ctx.reply("Failed to update global safety.")
            return
        await ctx.reply(f"Global safety {'enabled' if parsed else 'disabled'}.")

    @safety_group.command(name="module")
    @commands.check(_has_guild_control_ctx)
    async def safety_module(
        ctx: commands.Context,
        module: str,
        enabled: Optional[str] = None,
    ) -> None:
        """Prefix: Enable or disable a module. Accepts on/off strings."""
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        module_key = module.lower()
        if module_key not in SYSTEM_TOGGLES:
            await ctx.reply(f"Unknown module. Valid: {', '.join(SYSTEM_TOGGLES)}")
            return

        parsed = _parse_bool_flag(enabled)
        if parsed is None:
            await ctx.reply("Specify enabled as true/false or on/off.", mention_author=False)
            return

        set_module_enabled(ctx.guild, module_key, parsed)
        await ctx.reply(f"Module {module_key} {'enabled' if parsed else 'disabled'}.")

    @safety_group.group(name="exclude", invoke_without_command=True)
    @commands.check(_has_guild_control_ctx)
    async def safety_exclude(ctx: commands.Context) -> None:
        await ctx.reply("Usage: safety exclude add|remove|clear")

    @safety_exclude.command(name="add")
    @commands.check(_has_guild_control_ctx)
    async def safety_exclude_add(ctx: commands.Context, channel: discord.TextChannel) -> None:
        add_channel_exclusion(ctx.guild, channel)
        await ctx.reply(f"Excluded {channel.mention} from chaos actions.")

    @safety_exclude.command(name="remove")
    @commands.check(_has_guild_control_ctx)
    async def safety_exclude_remove(ctx: commands.Context, channel: discord.TextChannel) -> None:
        remove_channel_exclusion(ctx.guild, channel)
        await ctx.reply(f"Removed {channel.mention} from exclusions.")

    @safety_exclude.command(name="clear")
    @commands.check(_has_guild_control_ctx)
    async def safety_exclude_clear(ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Safety controls are only available in a server.")
            return
        clear_channel_exclusions(ctx.guild)
        await ctx.reply("Cleared all channel exclusions.")

    @safety_group.group(name="cooldown", invoke_without_command=True)
    @commands.check(_has_guild_control_ctx)
    async def safety_cooldown(ctx: commands.Context) -> None:
        await ctx.reply("Usage: safety cooldown set|clear <key> [seconds] [#channel]")

    @safety_cooldown.command(name="set")
    @commands.check(_has_guild_control_ctx)
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
    @commands.check(_has_guild_control_ctx)
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

    # -----------------
    # Slash (app) commands group
    # -----------------
    safety_app = app_commands.Group(name="safety", description="Server safety controls")

    @safety_app.command(name="status")
    async def app_safety_status(interaction: discord.Interaction) -> None:
        """Show safety status (slash)."""
        if interaction.guild is None:
            await interaction.response.send_message("Safety controls are only available in a server.", ephemeral=True)
            return
        toggles = get_module_toggles(interaction.guild)
        exclusions = get_guild_state(interaction.guild).get("channel_exclusions", set())
        status_lines = [
            f"Global enabled: {'on' if is_global_enabled() else 'off'}",
            f"Guild enabled: {'on' if is_guild_enabled(interaction.guild) else 'off'}",
            f"Excluded channels: {len(exclusions)}",
            "Module toggles:",
        ]
        for module in SYSTEM_TOGGLES:
            status_lines.append(f"- {module}: {'on' if toggles.get(module, True) else 'off'}")
        await interaction.response.send_message("\n".join(status_lines))

    @safety_app.command(name="enable")
    async def app_safety_enable(interaction: discord.Interaction) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        set_guild_enabled(interaction.guild, True)
        await interaction.response.send_message("Safety enabled for this server.")

    @safety_app.command(name="disable")
    async def app_safety_disable(interaction: discord.Interaction) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        set_guild_enabled(interaction.guild, False)
        await interaction.response.send_message("Safety disabled for this server.")

    @safety_app.command(name="global")
    async def app_safety_global(interaction: discord.Interaction, enabled: bool) -> None:
        """Set global safety (bot owner only) via slash with a boolean toggle."""
        if not _is_bot_owner(interaction.user.id):
            await interaction.response.send_message("Only the bot owner can change global safety.", ephemeral=True)
            return
        if not set_global_enabled(enabled, actor_id=interaction.user.id):
            await interaction.response.send_message("Failed to update global safety.", ephemeral=True)
            return
        await interaction.response.send_message(f"Global safety {'enabled' if enabled else 'disabled'}.")

    @safety_app.command(name="module")
    async def app_safety_module(interaction: discord.Interaction, module: str, enabled: bool) -> None:
        """Enable/disable a module via slash with a boolean toggle."""
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        module_key = module.lower()
        if module_key not in SYSTEM_TOGGLES:
            await interaction.response.send_message(f"Unknown module. Valid: {', '.join(SYSTEM_TOGGLES)}", ephemeral=True)
            return
        set_module_enabled(interaction.guild, module_key, enabled)
        await interaction.response.send_message(f"Module {module_key} {'enabled' if enabled else 'disabled'}.")

    # create exclude subgroup and register commands on it
    exclude_group = app_commands.Group(name="exclude", description="Manage excluded channels for safety")

    @exclude_group.command(name="add")
    async def app_safety_exclude_add(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        add_channel_exclusion(interaction.guild, channel)
        await interaction.response.send_message(f"Excluded {channel.mention} from chaos actions.")

    @exclude_group.command(name="remove")
    async def app_safety_exclude_remove(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        remove_channel_exclusion(interaction.guild, channel)
        await interaction.response.send_message(f"Removed {channel.mention} from exclusions.")

    @exclude_group.command(name="clear")
    async def app_safety_exclude_clear(interaction: discord.Interaction) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        clear_channel_exclusions(interaction.guild)
        await interaction.response.send_message("Cleared all channel exclusions.")

    safety_app.add_command(exclude_group)

    # create cooldown subgroup and register commands on it
    cooldown_group = app_commands.Group(name="cooldown", description="Manage safety cooldowns")

    @cooldown_group.command(name="set")
    async def app_safety_cooldown_set(
        interaction: discord.Interaction,
        key: str,
        seconds: float,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        until = set_cooldown(interaction.guild, key, seconds, channel=channel)
        remaining = max(0.0, until - time.monotonic())
        if channel:
            await interaction.response.send_message(f"Cooldown set for {key} in {channel.mention} ({remaining:.1f}s).")
        else:
            await interaction.response.send_message(f"Cooldown set for {key} in this server ({remaining:.1f}s).")

    @cooldown_group.command(name="clear")
    async def app_safety_cooldown_clear(
        interaction: discord.Interaction,
        key: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not _has_guild_control_interaction(interaction):
            await interaction.response.send_message("You do not have permission to perform this action.", ephemeral=True)
            return
        clear_cooldown(interaction.guild, key, channel=channel)
        if channel:
            await interaction.response.send_message(f"Cooldown cleared for {key} in {channel.mention}.")
        else:
            await interaction.response.send_message(f"Cooldown cleared for {key} in this server.")

    safety_app.add_command(cooldown_group)

    # Register the app command group on the bot's command tree
    try:
        bot.tree.add_command(safety_app)
    except Exception:
        # If registration fails (rare), ignore so prefix commands still work.
        pass
