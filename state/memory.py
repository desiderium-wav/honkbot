"""Goose Memory — Internal Memory and Grudge Tracking

THIS MODULE DEFINES NO COMMANDS.

This module stores and manages HonkBot’s memory.

- Track per-user honk counters
- Track per-channel honk activity
- Track users who have provoked the goose
- Track grudges and maintain provocation history and decay
- Maintain decay logic for honk counts
- Store recent honkified messages
- Maintain escalation thresholds (e.g., takeover eligibility)
- Track recent actions taken (anti-repetition)
- Maintain learned context keywords and topics

Memory supports both in-memory and persistent storage.
This module contains logic only and performs no Discord actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import time

DEFAULT_TAKEOVER_THRESHOLD = 10
DEFAULT_RECENT_ACTION_LIMIT = 10


@dataclass(frozen=True)
class RecentAction:
    action: str
    timestamp: float

_user_honk_counts: Dict[int, int] = {}
_channel_honk_activity: Dict[int, int] = {}
_cooldowns: Dict[Tuple[str, int], float] = {}
_takeover_thresholds: Dict[int, int] = {}
_recent_actions: Dict[int, List[RecentAction]] = {}
_honklocks: Dict[int, float] = {}
_echo_locks: Dict[int, float] = {}

_safety_state: Dict[int, Dict[str, Any]] = {}
_global_safety_enabled: bool = True


def get_user_honk_count(user_id: int) -> int:
    return _user_honk_counts.get(user_id, 0)


def set_user_honk_count(user_id: int, count: int) -> None:
    _user_honk_counts[user_id] = max(0, count)


def increment_user_honk_count(user_id: int, amount: int = 1) -> int:
    new_value = get_user_honk_count(user_id) + amount
    _user_honk_counts[user_id] = max(0, new_value)
    return _user_honk_counts[user_id]


def decay_user_honk_counts(amount: int = 1) -> None:
    if amount <= 0:
        return
    for user_id in list(_user_honk_counts.keys()):
        _user_honk_counts[user_id] = max(0, _user_honk_counts[user_id] - amount)


def reset_user_honk_count(user_id: int) -> None:
    _user_honk_counts.pop(user_id, None)


def reset_all_user_honk_counts() -> None:
    _user_honk_counts.clear()


def get_channel_honk_activity(channel_id: int) -> int:
    return _channel_honk_activity.get(channel_id, 0)


def set_channel_honk_activity(channel_id: int, count: int) -> None:
    _channel_honk_activity[channel_id] = max(0, count)


def increment_channel_honk_activity(channel_id: int, amount: int = 1) -> int:
    new_value = get_channel_honk_activity(channel_id) + amount
    _channel_honk_activity[channel_id] = max(0, new_value)
    return _channel_honk_activity[channel_id]


def decay_channel_honk_activity(amount: int = 1) -> None:
    if amount <= 0:
        return
    for channel_id in list(_channel_honk_activity.keys()):
        _channel_honk_activity[channel_id] = max(0, _channel_honk_activity[channel_id] - amount)


def reset_channel_honk_activity(channel_id: int) -> None:
    _channel_honk_activity.pop(channel_id, None)


def reset_all_channel_honk_activity() -> None:
    _channel_honk_activity.clear()


def get_cooldown(key: str, target_id: int) -> Optional[float]:
    return _cooldowns.get((key, target_id))


def set_cooldown(key: str, target_id: int, until_timestamp: float) -> None:
    _cooldowns[(key, target_id)] = until_timestamp


def clear_cooldown(key: str, target_id: int) -> None:
    _cooldowns.pop((key, target_id), None)


def is_on_cooldown(key: str, target_id: int, now: Optional[float] = None) -> bool:
    timestamp = get_cooldown(key, target_id)
    if timestamp is None:
        return False
    if now is None:
        now = time.time()
    return now < timestamp


def reset_all_cooldowns() -> None:
    _cooldowns.clear()


def get_takeover_threshold(channel_id: int) -> int:
    return _takeover_thresholds.get(channel_id, DEFAULT_TAKEOVER_THRESHOLD)


def set_takeover_threshold(channel_id: int, threshold: int) -> None:
    _takeover_thresholds[channel_id] = max(1, threshold)


def is_takeover_ready(channel_id: int, honk_count: int) -> bool:
    return honk_count >= get_takeover_threshold(channel_id)


def reset_takeover_threshold(channel_id: int) -> None:
    _takeover_thresholds.pop(channel_id, None)


def reset_all_takeover_thresholds() -> None:
    _takeover_thresholds.clear()


def get_recent_actions(user_id: int) -> List[RecentAction]:
    return list(_recent_actions.get(user_id, []))


def add_recent_action(
    user_id: int,
    action: str,
    timestamp: Optional[float] = None,
    limit: int = DEFAULT_RECENT_ACTION_LIMIT,
) -> None:
    if timestamp is None:
        timestamp = time.time()
    actions = _recent_actions.setdefault(user_id, [])
    actions.append(RecentAction(action=action, timestamp=timestamp))
    if limit > 0:
        _recent_actions[user_id] = actions[-limit:]


def clear_recent_actions(user_id: int) -> None:
    _recent_actions.pop(user_id, None)


def reset_all_recent_actions() -> None:
    _recent_actions.clear()


def set_honklock(user_id: int, locked_at: Optional[float] = None) -> float:
    if locked_at is None:
        locked_at = time.time()
    _honklocks[user_id] = locked_at
    return locked_at


def clear_honklock(user_id: int) -> None:
    _honklocks.pop(user_id, None)


def is_honklocked(user_id: int) -> bool:
    return user_id in _honklocks


def get_honklock_time(user_id: int) -> Optional[float]:
    return _honklocks.get(user_id)


def get_all_honklocks() -> Dict[int, float]:
    return dict(_honklocks)


def reset_all_honklocks() -> None:
    _honklocks.clear()


def set_echolock(user_id: int, locked_at: Optional[float] = None) -> float:
    if locked_at is None:
        locked_at = time.time()
    _echo_locks[user_id] = locked_at
    return locked_at


def clear_echolock(user_id: int) -> None:
    _echo_locks.pop(user_id, None)


def is_echolocked(user_id: int) -> bool:
    return user_id in _echo_locks


def get_echolock_time(user_id: int) -> Optional[float]:
    return _echo_locks.get(user_id)


def get_all_echolocks() -> Dict[int, float]:
    return dict(_echo_locks)


def reset_all_echolocks() -> None:
    _echo_locks.clear()


def _default_safety_state() -> Dict[str, Any]:
    return {
        "enabled": True,
        "channel_exclusions": set(),
        "immunity_roles": set(),
        "module_toggles": {},
        "cooldowns": {},
    }


def get_safety_state(guild_id: int) -> Dict[str, Any]:
    state = _safety_state.get(guild_id)
    if state is None:
        state = _default_safety_state()
        _safety_state[guild_id] = state
        return state
    state.setdefault("enabled", True)
    state.setdefault("channel_exclusions", set())
    state.setdefault("immunity_roles", set())
    state.setdefault("module_toggles", {})
    state.setdefault("cooldowns", {})
    return state


def reset_safety_state(guild_id: int) -> None:
    _safety_state.pop(guild_id, None)


def reset_all_safety_state() -> None:
    _safety_state.clear()


def get_global_safety_enabled() -> bool:
    return _global_safety_enabled


def set_global_safety_enabled(enabled: bool) -> None:
    global _global_safety_enabled
    _global_safety_enabled = bool(enabled)


def reset_all_state() -> None:
    reset_all_user_honk_counts()
    reset_all_channel_honk_activity()
    reset_all_cooldowns()
    reset_all_takeover_thresholds()
    reset_all_recent_actions()
    reset_all_honklocks()
    reset_all_echolocks()
    reset_all_safety_state()
    set_global_safety_enabled(True)