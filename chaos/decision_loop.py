"""
Chaos Decision Loop — Autonomous Goose Behavior Scheduler

THIS MODULE DEFINES BACKGROUND TASKS ONLY.

Responsibilities:
- Periodically evaluate server activity
- Consult Goose Brain and Memory
- Increase chaos probability based on honk density
- Trigger honkify events, takeovers, and media bursts
- Respect cooldowns and safety control
- Roll weighted probabilities for chaos events
- Trigger random actions via other systems

This loop gives HonkBot its “mind of its own.”
No commands are defined here.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Dict, Optional, Sequence, Tuple

import discord

from chaos import random_events
from safety import controls
from state import goose_brain, memory
from utils import timers
from voice import behavior as voice_behavior

try:
    # Shared activity tracker maintained elsewhere (via on_message)
    # Expected shape: recent_message_counts[guild_id][channel_id] = count
    from activity.tracker import recent_message_counts  # type: ignore
except Exception:
    recent_message_counts: Dict[int, Dict[int, int]] = {}

logger = logging.getLogger(__name__)

# ---------------------------
# Configuration (hardcoded defaults)
# ---------------------------
MIN_CYCLE_SECONDS = 20.0
MAX_CYCLE_SECONDS = 45.0

GUILD_COOLDOWN_KEY = "chaos_guild_cycle"
GUILD_COOLDOWN_SECONDS = 25.0

BASE_ACTION_CHANCE = 0.08
CHAOS_WEIGHT = 0.45
ACTIVITY_WEIGHT = 0.35
HONK_WEIGHT = 0.5
PROVOCATION_WEIGHT = 0.4

ACTIVITY_MESSAGE_TARGET = 25  # higher = less sensitive
MIN_ACTIVITY_SCORE = 0.05

VOICE_ACTION_WEIGHT = 0.18
HONKIFY_ACTION_WEIGHT = 0.36
TAKEOVER_ACTION_WEIGHT = 0.28
FLOOD_ACTION_WEIGHT = 0.18

# ---------------------------
# Module state
# ---------------------------
_task: Optional[asyncio.Task] = None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _safe_call(func, *args) -> Tuple[bool, Optional[bool]]:
    try:
        result = func(*args)
        return True, bool(result) if isinstance(result, bool) else None
    except TypeError:
        return False, None
    except Exception:
        return True, None


def _safety_allows(guild: discord.Guild, channel: Optional[discord.TextChannel]) -> bool:
    if not hasattr(controls, "__dict__"):
        return True

    for attr in ("is_enabled", "is_guild_enabled"):
        func = getattr(controls, attr, None)
        if callable(func):
            called, result = _safe_call(func, guild)
            if not called:
                called, result = _safe_call(func, guild.id)
            if result is False:
                return False

    for attr in ("is_system_enabled", "is_module_enabled"):
        func = getattr(controls, attr, None)
        if callable(func):
            called, result = _safe_call(func, guild, "chaos")
            if not called:
                called, result = _safe_call(func, guild.id, "chaos")
            if result is False:
                return False

    if channel:
        for attr in ("is_channel_allowed", "is_channel_enabled", "channel_allowed"):
            func = getattr(controls, attr, None)
            if callable(func):
                called, result = _safe_call(func, guild, channel)
                if not called:
                    called, result = _safe_call(func, guild.id, channel.id)
                if result is False:
                    return False

    return True


def _activity_snapshot(guild: discord.Guild) -> Dict[int, int]:
    return dict(recent_message_counts.get(guild.id, {}))


def _activity_score(counts: Dict[int, int]) -> float:
    if not counts:
        return MIN_ACTIVITY_SCORE
    total = sum(max(0, count) for count in counts.values())
    return _clamp(total / max(1, ACTIVITY_MESSAGE_TARGET), MIN_ACTIVITY_SCORE, 1.0)


def _select_active_channel(
    guild: discord.Guild,
    counts: Dict[int, int],
) -> Optional[discord.TextChannel]:
    if not counts:
        return None

    weighted: Sequence[Tuple[discord.TextChannel, int]] = []
    for channel_id, count in counts.items():
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel) and count > 0:
            weighted.append((channel, count))

    if not weighted:
        return None

    channels, weights = zip(*weighted)
    return random.choices(list(channels), weights=list(weights), k=1)[0]


def _honk_density(channel: Optional[discord.TextChannel]) -> float:
    if not channel:
        return 0.0
    honk_count = memory.get_channel_honk_activity(channel.id)
    threshold = memory.get_takeover_threshold(channel.id)
    return _clamp(honk_count / max(1, threshold))


def _provocation_level(guild: discord.Guild) -> float:
    try:
        from retaliation import engine as retaliation_engine  # type: ignore
    except Exception:
        return 0.0

    for attr in ("get_guild_provocation", "get_provocation_level", "get_provocation_score"):
        func = getattr(retaliation_engine, attr, None)
        if callable(func):
            try:
                return _clamp(float(func(guild)))
            except Exception:
                try:
                    return _clamp(float(func(guild.id)))
                except Exception:
                    return 0.0
    return 0.0


def _overall_action_chance(
    state: goose_brain.GooseState,
    activity_score: float,
    honk_density: float,
    provocation: float,
) -> float:
    return _clamp(
        BASE_ACTION_CHANCE
        + (state.chaos * CHAOS_WEIGHT)
        + (activity_score * ACTIVITY_WEIGHT)
        + (honk_density * HONK_WEIGHT)
        + (provocation * PROVOCATION_WEIGHT)
    )


def _weighted_action(
    state: goose_brain.GooseState,
    honk_density: float,
) -> str:
    weights = {
        "voice": VOICE_ACTION_WEIGHT,
        "honkify": HONKIFY_ACTION_WEIGHT,
        "takeover": TAKEOVER_ACTION_WEIGHT,
        "flood": FLOOD_ACTION_WEIGHT,
    }

    if state.mood == goose_brain.Mood.CHAOTIC:
        weights["takeover"] *= 1.25
        weights["honkify"] *= 1.1
    elif state.mood == goose_brain.Mood.SERENE:
        weights["voice"] *= 1.1
        weights["flood"] *= 0.85

    if honk_density >= 1.0:
        weights["takeover"] *= 1.4

    actions, action_weights = zip(*weights.items())
    return random.choices(list(actions), weights=list(action_weights), k=1)[0]


async def _execute_action(
    action: str,
    *,
    guild: discord.Guild,
    channel: Optional[discord.TextChannel],
    state: goose_brain.GooseState,
    activity_score: float,
    honk_density: float,
    provocation: float,
) -> bool:
    if action == "voice":
        voice_action = getattr(voice_behavior, "random_voice_action", None)
        if callable(voice_action):
            context = {
                "mood": state.mood.value,
                "chaos": state.chaos,
                "activity_score": activity_score,
                "honk_density": honk_density,
                "provocation": provocation,
            }
            await voice_action(guild, context)
            return True
        return False

    if not channel:
        return False

    if action == "takeover":
        return await random_events.channel_takeover(channel)

    if action == "honkify":
        members = [m for m in channel.members if not m.bot]
        return await random_events.honkify_burst(channel, members)

    if action == "flood":
        return await random_events.message_flood(channel)

    return False


async def _run_for_guild(bot: discord.Client, guild: discord.Guild) -> None:
    if memory.is_on_cooldown(GUILD_COOLDOWN_KEY, guild.id):
        return

    counts = _activity_snapshot(guild)
    activity_score = _activity_score(counts)
    channel = _select_active_channel(guild, counts)
    honk_density = _honk_density(channel)
    provocation = _provocation_level(guild)

    state = goose_brain.tick()

    if not _safety_allows(guild, channel):
        logger.info(
            "chaos_decision_loop",
            extra={"guild_id": guild.id, "action": "blocked", "reason": "safety"},
        )
        return

    chance = _overall_action_chance(state, activity_score, honk_density, provocation)
    if random.random() > chance:
        logger.info(
            "chaos_decision_loop",
            extra={"guild_id": guild.id, "action": "none", "chance": chance},
        )
        return

    action = _weighted_action(state, honk_density)
    performed = await _execute_action(
        action,
        guild=guild,
        channel=channel,
        state=state,
        activity_score=activity_score,
        honk_density=honk_density,
        provocation=provocation,
    )

    if performed:
        memory.set_cooldown(GUILD_COOLDOWN_KEY, guild.id, timers._now() + GUILD_COOLDOWN_SECONDS)
        logger.info(
            "chaos_decision_loop",
            extra={
                "guild_id": guild.id,
                "action": action,
                "channel_id": channel.id if channel else None,
                "chance": chance,
                "activity_score": activity_score,
                "honk_density": honk_density,
                "provocation": provocation,
                "mood": state.mood.value,
            },
        )


async def _loop(bot: discord.Client) -> None:
    try:
        while True:
            for guild in list(bot.guilds):
                try:
                    await _run_for_guild(bot, guild)
                except Exception:
                    logger.exception(
                        "chaos_decision_loop_error",
                        extra={"guild_id": getattr(guild, "id", None)},
                    )
            await timers.randomized_delay(MIN_CYCLE_SECONDS, MAX_CYCLE_SECONDS)
    except asyncio.CancelledError:
        logger.info("chaos_decision_loop_cancelled")
        raise


async def start(bot: discord.Client) -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop(bot))


async def stop() -> None:
    global _task
    if not _task:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
