"""
Voice Behavior — Voice Channel Chaos System

THIS MODULE DEFINES AUTONOMOUS BEHAVIOR AND OPTIONAL HELPER COMMANDS.

Autonomous behavior:
- Randomly join active voice channels silently
- Leave after a random duration
- Join inactive channels and idle
- Move a random user, then immediately leave

Optional admin/helper commands:
- Force the goose to leave voice
- Temporarily disable voice chaos

Voice actions are semi-rare, timed, and state-dependent.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import discord

from safety import controls
from utils import timers

__all__ = [
    "random_voice_action",
    "leave_if_connected",
]

VOICE_MODULE = "voice"
COOLDOWN_KEY = "voice_action"

GUILD_COOLDOWN_SECONDS = 120.0
CHANNEL_COOLDOWN_SECONDS = 90.0

IDLE_MIN_SECONDS = 10.0
IDLE_MAX_SECONDS = 30.0

ACTIVE_JOIN_CHANCE = 0.55
INACTIVE_JOIN_CHANCE = 0.30
MOVE_USER_CHANCE = 0.15

SLEEP_TICK_SECONDS = 1.0


def _get_bot_member(guild: discord.Guild) -> Optional[discord.Member]:
    return getattr(guild, "me", None)


def _is_normal_voice_channel(channel: discord.abc.GuildChannel) -> bool:
    if isinstance(channel, discord.StageChannel):
        return False
    if isinstance(channel, discord.VoiceChannel):
        return True
    if getattr(channel, "type", None) == discord.ChannelType.voice:
        return True
    return False


def _is_afk_channel(guild: discord.Guild, channel: discord.abc.GuildChannel) -> bool:
    return guild.afk_channel is not None and guild.afk_channel.id == channel.id


def _has_connect_permissions(channel: discord.VoiceChannel, bot_member: discord.Member) -> bool:
    perms = channel.permissions_for(bot_member)
    return bool(perms.connect)


def _has_move_permissions(channel: discord.VoiceChannel, bot_member: discord.Member) -> bool:
    perms = channel.permissions_for(bot_member)
    return bool(perms.move_members)


def _has_required_permissions(channel: discord.VoiceChannel, bot_member: discord.Member) -> bool:
    perms = channel.permissions_for(bot_member)
    return bool(perms.connect and perms.move_members)


def _non_bot_members(channel: discord.VoiceChannel) -> List[discord.Member]:
    return [member for member in channel.members if not member.bot]


def _channel_full(channel: discord.VoiceChannel) -> bool:
    if channel.user_limit and channel.user_limit > 0:
        return len(channel.members) >= channel.user_limit
    return False


def _safety_allows_channel(guild: discord.Guild, channel: discord.abc.GuildChannel) -> bool:
    return controls.safety_allows(guild=guild, channel=channel, module=VOICE_MODULE)


def _eligible_voice_channels(guild: discord.Guild) -> List[discord.VoiceChannel]:
    bot_member = _get_bot_member(guild)
    if bot_member is None:
        return []

    channels: List[discord.VoiceChannel] = []
    for channel in guild.voice_channels:
        if not _is_normal_voice_channel(channel):
            continue
        if _is_afk_channel(guild, channel):
            continue
        if not _safety_allows_channel(guild, channel):
            continue
        if not _has_required_permissions(channel, bot_member):
            continue
        channels.append(channel)
    return channels


def _eligible_move_target_channels(
    guild: discord.Guild,
    source: discord.VoiceChannel,
) -> List[discord.VoiceChannel]:
    bot_member = _get_bot_member(guild)
    if bot_member is None:
        return []

    targets: List[discord.VoiceChannel] = []
    for channel in guild.voice_channels:
        if channel.id == source.id:
            continue
        if not _is_normal_voice_channel(channel):
            continue
        if _is_afk_channel(guild, channel):
            continue
        if not _safety_allows_channel(guild, channel):
            continue
        if _channel_full(channel):
            continue
        if not _has_connect_permissions(channel, bot_member):
            continue
        targets.append(channel)
    return targets


def _eligible_move_members(
    guild: discord.Guild,
    channel: discord.VoiceChannel,
) -> List[discord.Member]:
    members = []
    for member in channel.members:
        if member.bot:
            continue
        if guild.owner_id and member.id == guild.owner_id:
            continue
        if controls.user_has_immunity(member):
            continue
        members.append(member)
    return members


def _select_action(context: Optional[Dict[str, object]]) -> str:
    chaos = 0.0
    if context:
        try:
            chaos = float(context.get("chaos", 0.0))
        except (TypeError, ValueError):
            chaos = 0.0

    move_chance = MOVE_USER_CHANCE
    if chaos >= 0.75:
        move_chance = 0.2
    elif chaos <= 0.25:
        move_chance = 0.1

    roll = random.random()
    if roll < move_chance:
        return "move"
    if roll < move_chance + ACTIVE_JOIN_CHANCE:
        return "active_idle"
    return "inactive_idle"


async def _connect_to_channel(channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
    voice_client = channel.guild.voice_client
    try:
        if voice_client and voice_client.is_connected():
            if voice_client.channel and voice_client.channel.id == channel.id:
                return voice_client
            await voice_client.move_to(channel)
            return voice_client
        return await channel.connect()
    except Exception:
        return None


async def _disconnect_from_guild(guild: discord.Guild) -> bool:
    voice_client = guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return False
    try:
        await voice_client.disconnect()
        return True
    except Exception:
        return False


async def leave_if_connected(guild: discord.Guild) -> bool:
    return await _disconnect_from_guild(guild)


async def _linger_in_channel(
    channel: discord.VoiceChannel,
    *,
    leave_on_activity: bool,
) -> bool:
    voice_client = await _connect_to_channel(channel)
    if not voice_client:
        return False

    duration = timers.randomized_delay_value(IDLE_MIN_SECONDS, IDLE_MAX_SECONDS)
    end_at = time.monotonic() + duration

    while time.monotonic() < end_at:
        if leave_on_activity and _non_bot_members(channel):
            break
        await asyncio.sleep(SLEEP_TICK_SECONDS)

    await _disconnect_from_guild(channel.guild)
    return True


async def _idle_in_active_channel(channel: discord.VoiceChannel) -> bool:
    if not _non_bot_members(channel):
        return False
    return await _linger_in_channel(channel, leave_on_activity=False)


async def _idle_in_empty_channel(channel: discord.VoiceChannel) -> bool:
    if _non_bot_members(channel):
        return False
    return await _linger_in_channel(channel, leave_on_activity=True)


async def _move_random_member(guild: discord.Guild) -> bool:
    bot_member = _get_bot_member(guild)
    if bot_member is None:
        return False

    candidate_channels = [
        channel
        for channel in _eligible_voice_channels(guild)
        if _non_bot_members(channel)
    ]
    if not candidate_channels:
        return False

    source_channel = random.choice(candidate_channels)
    if controls.cooldown_active(guild, COOLDOWN_KEY, channel=source_channel):
        return False

    if not _has_move_permissions(source_channel, bot_member):
        return False

    eligible_members = _eligible_move_members(guild, source_channel)
    if not eligible_members:
        return False

    target_channels = _eligible_move_target_channels(guild, source_channel)
    if not target_channels:
        return False

    member = random.choice(eligible_members)
    target_channel = random.choice(target_channels)

    voice_client = await _connect_to_channel(source_channel)
    if not voice_client:
        return False

    try:
        await member.move_to(target_channel)
    except Exception:
        await _disconnect_from_guild(guild)
        return False

    await _disconnect_from_guild(guild)
    return True


async def random_voice_action(
    guild: discord.Guild,
    context: Optional[Dict[str, object]] = None,
) -> bool:
    if not controls.safety_allows(guild=guild, module=VOICE_MODULE):
        return False
    if controls.cooldown_active(guild, COOLDOWN_KEY):
        return False

    channels = _eligible_voice_channels(guild)
    if not channels:
        return False

    action = _select_action(context)
    performed = False
    chosen_channel: Optional[discord.VoiceChannel] = None

    if action == "move":
        performed = await _move_random_member(guild)
    elif action == "active_idle":
        active_channels = [channel for channel in channels if _non_bot_members(channel)]
        if active_channels:
            chosen_channel = random.choice(active_channels)
            if not controls.cooldown_active(guild, COOLDOWN_KEY, channel=chosen_channel):
                performed = await _idle_in_active_channel(chosen_channel)
    else:
        idle_channels = [channel for channel in channels if not _non_bot_members(channel)]
        if idle_channels:
            chosen_channel = random.choice(idle_channels)
            if not controls.cooldown_active(guild, COOLDOWN_KEY, channel=chosen_channel):
                performed = await _idle_in_empty_channel(chosen_channel)

    if performed:
        controls.set_cooldown(guild, COOLDOWN_KEY, GUILD_COOLDOWN_SECONDS)
        if chosen_channel:
            controls.set_cooldown(
                guild,
                COOLDOWN_KEY,
                CHANNEL_COOLDOWN_SECONDS,
                channel=chosen_channel,
            )
    return performed
