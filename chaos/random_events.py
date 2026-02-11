"""
Random Chaos Events — Autonomous Action Definitions

THIS MODULE DEFINES NO COMMANDS.

Defines autonomous chaos events such as:
  - Random honkify or echo on active users
  - Sudden messages or pings
  - Channel takeover events ("channel honkjacked"
  - Media bursts tied to honk escalation 
  - Voice channel disruptions
  - Random drive-by goose interruptions in chat

Takeover Event:
- Triggered when per-channel or per-user honk count crosses a threshold
- Posts "CHANNEL HONKJACKED"
- Emits bursts of HONKs, emojis, and GIFs
- Enforced per-channel cooldow

Events are selected and triggered by the Chaos Decision Loop. Expose callable event functions to the decision loop.

This module does not schedule itself.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import random
import time

import discord

from locks import honkify
from state import memory
from utils import timers
from utils.text import safe_truncate

__all__ = [
    "honkify_burst",
    "channel_takeover",
    "message_flood",
]

MAX_MESSAGE_LENGTH = 1900

COOLDOWN_HONKIFY_BURST = "chaos_honkify_burst"
COOLDOWN_TAKEOVER = "chaos_takeover"
COOLDOWN_MESSAGE_FLOOD = "chaos_message_flood"

DEFAULT_HONKIFY_BURST_COUNT = 3
DEFAULT_HONKIFY_COOLDOWN_SECONDS = 60.0

DEFAULT_TAKEOVER_BURST_LINES = 6
DEFAULT_TAKEOVER_COOLDOWN_SECONDS = 300.0

DEFAULT_FLOOD_COUNT = 6
DEFAULT_FLOOD_COOLDOWN_SECONDS = 90.0

DEFAULT_MIN_DELAY_SECONDS = 0.4
DEFAULT_MAX_DELAY_SECONDS = 1.2

HONKIFY_PROMPTS = [
    "{name}, the goose demands tribute.",
    "{name} has been selected for honkification.",
    "The chaos goose eyes {name}.",
    "{name} has been honked by fate.",
]

TAKEOVER_LINES = [
    "HONK HONK HONK",
    "🪿🪿🪿",
    "H O N K",
    "HONK!!!",
    "🪿 HONK 🪿",
    "H O N K !",
    "HONK HONK",
]

FLOOD_LINES = [
    "honk",
    "HONK",
    "honk honk",
    "H O N K",
    "🪿",
    "🪿 HONK",
]


def _is_on_cooldown(key: str, channel_id: int) -> bool:
    return memory.is_on_cooldown(key, channel_id)


def _trigger_cooldown(key: str, channel_id: int, *, seconds: float) -> None:
    memory.set_cooldown(key, channel_id, time.time() + seconds)


async def honkify_burst(
    channel: discord.TextChannel,
    members: Sequence[discord.Member],
    *,
    burst_count: int = DEFAULT_HONKIFY_BURST_COUNT,
    cooldown_seconds: float = DEFAULT_HONKIFY_COOLDOWN_SECONDS,
    min_delay_seconds: float = DEFAULT_MIN_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
) -> bool:
    if not channel or not members:
        return False
    if _is_on_cooldown(COOLDOWN_HONKIFY_BURST, channel.id):
        return False

    for _ in range(max(1, burst_count)):
        target = random.choice(members)
        base = random.choice(HONKIFY_PROMPTS).format(name=target.display_name)
        outcome = honkify.honkify_message(
            base,
            user_id=target.id,
            channel_id=channel.id,
            force=True,
        )
        content = outcome.honkified_text if outcome and outcome.honkified_text else base
        content = safe_truncate(content, MAX_MESSAGE_LENGTH)
        await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
        await timers.randomized_delay(min_delay_seconds, max_delay_seconds)

    _trigger_cooldown(COOLDOWN_HONKIFY_BURST, channel.id, seconds=cooldown_seconds)
    return True


async def channel_takeover(
    channel: discord.TextChannel,
    *,
    burst_lines: int = DEFAULT_TAKEOVER_BURST_LINES,
    cooldown_seconds: float = DEFAULT_TAKEOVER_COOLDOWN_SECONDS,
    min_delay_seconds: float = DEFAULT_MIN_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
) -> bool:
    if not channel:
        return False
    if _is_on_cooldown(COOLDOWN_TAKEOVER, channel.id):
        return False

    honk_count = memory.get_channel_honk_activity(channel.id)
    if not memory.is_takeover_ready(channel.id, honk_count):
        return False

    await channel.send("CHANNEL HONKJACKED", allowed_mentions=discord.AllowedMentions.none())
    await timers.randomized_delay(0.25, 0.75)

    for _ in range(max(1, burst_lines)):
        line = random.choice(TAKEOVER_LINES)
        await channel.send(line, allowed_mentions=discord.AllowedMentions.none())
        await timers.randomized_delay(min_delay_seconds, max_delay_seconds)

    memory.reset_channel_honk_activity(channel.id)
    _trigger_cooldown(COOLDOWN_TAKEOVER, channel.id, seconds=cooldown_seconds)
    return True


async def message_flood(
    channel: discord.TextChannel,
    *,
    lines: Iterable[str] | None = None,
    flood_count: int = DEFAULT_FLOOD_COUNT,
    cooldown_seconds: float = DEFAULT_FLOOD_COOLDOWN_SECONDS,
    min_delay_seconds: float = 0.2,
    max_delay_seconds: float = 0.8,
) -> bool:
    if not channel:
        return False
    if _is_on_cooldown(COOLDOWN_MESSAGE_FLOOD, channel.id):
        return False

    pool = [line for line in (lines or FLOOD_LINES) if line]
    if not pool:
        return False

    for _ in range(max(1, flood_count)):
        line = safe_truncate(random.choice(pool), MAX_MESSAGE_LENGTH)
        await channel.send(line, allowed_mentions=discord.AllowedMentions.none())
        await timers.randomized_delay(min_delay_seconds, max_delay_seconds)

    _trigger_cooldown(COOLDOWN_MESSAGE_FLOOD, channel.id, seconds=cooldown_seconds)
    return True
