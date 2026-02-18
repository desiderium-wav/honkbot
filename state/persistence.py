"""
State Memory Persistence — Save and Load Bot State from Oracle DB

This module handles persistence for all bot state in state/memory.py:
- User honk counts
- Channel honk activity
- Cooldowns
- Takeover thresholds
- Recent actions
- Honklocks and echolocks
- Safety state
- Global safety enabled flag
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import db_layer

logger = logging.getLogger(__name__)


def load_all_state() -> None:
    """
    Load all persisted state from database into memory.
    Called on bot startup.
    """
    try:
        _load_user_honk_counts()
        _load_channel_honk_activity()
        _load_cooldowns()
        _load_takeover_thresholds()
        _load_recent_actions()
        _load_honklocks()
        _load_echolocks()
        _load_safety_state()
        _load_global_safety_enabled()
        logger.info("Successfully loaded all state from database")
    except Exception as e:
        logger.error(f"Error loading state from database: {e}", exc_info=True)


def _load_user_honk_counts() -> None:
    """Load user honk counts from database."""
    from state import memory
    
    rows = db_layer.fetch_all("SELECT user_id, honk_count FROM honkbot_user_honk_counts")
    for user_id, honk_count in rows:
        memory.set_user_honk_count(int(user_id), int(honk_count))
    logger.debug(f"Loaded {len(rows)} user honk counts")


def save_user_honk_count(user_id: int, count: int) -> None:
    """Save a user's honk count to database."""
    try:
        if count > 0:
            db_layer.upsert(
                "honkbot_user_honk_counts",
                {"user_id": user_id},
                {"honk_count": count}
            )
        else:
            # Remove zero counts to keep table clean
            db_layer.delete_rows("honkbot_user_honk_counts", {"user_id": user_id})
    except Exception as e:
        logger.error(f"Error saving user honk count: {e}", exc_info=True)


def _load_channel_honk_activity() -> None:
    """Load channel honk activity from database."""
    from state import memory
    
    rows = db_layer.fetch_all("SELECT channel_id, activity_count FROM honkbot_channel_honk_activity")
    for channel_id, activity_count in rows:
        memory.set_channel_honk_activity(int(channel_id), int(activity_count))
    logger.debug(f"Loaded {len(rows)} channel honk activities")


def save_channel_honk_activity(channel_id: int, count: int) -> None:
    """Save channel honk activity to database."""
    try:
        if count > 0:
            db_layer.upsert(
                "honkbot_channel_honk_activity",
                {"channel_id": channel_id},
                {"activity_count": count}
            )
        else:
            db_layer.delete_rows("honkbot_channel_honk_activity", {"channel_id": channel_id})
    except Exception as e:
        logger.error(f"Error saving channel honk activity: {e}", exc_info=True)


def _load_cooldowns() -> None:
    """Load cooldowns from database."""
    from state import memory
    
    # Only load cooldowns that haven't expired
    now = time.time()
    rows = db_layer.fetch_all(
        "SELECT cooldown_key, target_id, until_timestamp FROM honkbot_cooldowns WHERE until_timestamp > :now",
        {"now": now}
    )
    for cooldown_key, target_id, until_timestamp in rows:
        memory.set_cooldown(str(cooldown_key), int(target_id), float(until_timestamp))
    logger.debug(f"Loaded {len(rows)} active cooldowns")
    
    # Clean up expired cooldowns
    try:
        with db_layer.db_cursor() as cursor:
            cursor.execute("DELETE FROM honkbot_cooldowns WHERE until_timestamp < :now", {"now": now})
            if cursor.rowcount > 0:
                logger.debug(f"Cleaned up {cursor.rowcount} expired cooldowns")
    except Exception as e:
        logger.error(f"Error cleaning expired cooldowns: {e}")


def save_cooldown(key: str, target_id: int, until_timestamp: float) -> None:
    """Save a cooldown to database."""
    try:
        db_layer.upsert(
            "honkbot_cooldowns",
            {"cooldown_key": key, "target_id": target_id},
            {"until_timestamp": until_timestamp}
        )
    except Exception as e:
        logger.error(f"Error saving cooldown: {e}", exc_info=True)


def clear_cooldown(key: str, target_id: int) -> None:
    """Remove a cooldown from database."""
    try:
        db_layer.delete_rows("honkbot_cooldowns", {"cooldown_key": key, "target_id": target_id})
    except Exception as e:
        logger.error(f"Error clearing cooldown: {e}", exc_info=True)


def _load_takeover_thresholds() -> None:
    """Load takeover thresholds from database."""
    from state import memory
    
    rows = db_layer.fetch_all("SELECT channel_id, threshold_value FROM honkbot_takeover_thresholds")
    for channel_id, threshold_value in rows:
        memory.set_takeover_threshold(int(channel_id), int(threshold_value))
    logger.debug(f"Loaded {len(rows)} takeover thresholds")


def save_takeover_threshold(channel_id: int, threshold: int) -> None:
    """Save a takeover threshold to database."""
    try:
        db_layer.upsert(
            "honkbot_takeover_thresholds",
            {"channel_id": channel_id},
            {"threshold_value": threshold}
        )
    except Exception as e:
        logger.error(f"Error saving takeover threshold: {e}", exc_info=True)


def _load_recent_actions() -> None:
    """Load recent actions from database."""
    from state import memory
    
    # Load recent actions (last 24 hours)
    cutoff = time.time() - 86400
    rows = db_layer.fetch_all(
        "SELECT user_id, action_name, action_timestamp FROM honkbot_recent_actions WHERE action_timestamp > :cutoff ORDER BY action_timestamp",
        {"cutoff": cutoff}
    )
    
    for user_id, action_name, action_timestamp in rows:
        memory.add_recent_action(int(user_id), str(action_name), float(action_timestamp))
    logger.debug(f"Loaded {len(rows)} recent actions")


def save_recent_action(user_id: int, action: str, timestamp: float) -> None:
    """Save a recent action to database."""
    try:
        with db_layer.db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO honkbot_recent_actions (user_id, action_name, action_timestamp) VALUES (:user_id, :action, :ts)",
                {"user_id": user_id, "action": action, "ts": timestamp}
            )
        
        # Clean up old actions (older than 24 hours)
        cutoff = time.time() - 86400
        with db_layer.db_cursor() as cursor:
            cursor.execute("DELETE FROM honkbot_recent_actions WHERE action_timestamp < :cutoff", {"cutoff": cutoff})
    except Exception as e:
        logger.error(f"Error saving recent action: {e}", exc_info=True)


def _load_honklocks() -> None:
    """Load honklocks from database."""
    from state import memory
    
    rows = db_layer.fetch_all("SELECT user_id, locked_at FROM honkbot_honklocks")
    for user_id, locked_at in rows:
        memory.set_honklock(int(user_id), float(locked_at))
    logger.debug(f"Loaded {len(rows)} honklocks")


def save_honklock(user_id: int, locked_at: float) -> None:
    """Save a honklock to database."""
    try:
        db_layer.upsert(
            "honkbot_honklocks",
            {"user_id": user_id},
            {"locked_at": locked_at}
        )
    except Exception as e:
        logger.error(f"Error saving honklock: {e}", exc_info=True)


def clear_honklock(user_id: int) -> None:
    """Remove a honklock from database."""
    try:
        db_layer.delete_rows("honkbot_honklocks", {"user_id": user_id})
    except Exception as e:
        logger.error(f"Error clearing honklock: {e}", exc_info=True)


def _load_echolocks() -> None:
    """Load echolocks from database."""
    from state import memory
    
    rows = db_layer.fetch_all("SELECT user_id, locked_at FROM honkbot_echolocks")
    for user_id, locked_at in rows:
        memory.set_echolock(int(user_id), float(locked_at))
    logger.debug(f"Loaded {len(rows)} echolocks")


def save_echolock(user_id: int, locked_at: float) -> None:
    """Save an echolock to database."""
    try:
        db_layer.upsert(
            "honkbot_echolocks",
            {"user_id": user_id},
            {"locked_at": locked_at}
        )
    except Exception as e:
        logger.error(f"Error saving echolock: {e}", exc_info=True)


def clear_echolock(user_id: int) -> None:
    """Remove an echolock from database."""
    try:
        db_layer.delete_rows("honkbot_echolocks", {"user_id": user_id})
    except Exception as e:
        logger.error(f"Error clearing echolock: {e}", exc_info=True)


def _load_safety_state() -> None:
    """Load safety state from database."""
    from state import memory
    
    rows = db_layer.fetch_all(
        "SELECT guild_id, enabled, channel_exclusions, immunity_roles, module_toggles, cooldowns FROM honkbot_safety_state"
    )
    
    for guild_id, enabled, channel_exclusions, immunity_roles, module_toggles, cooldowns in rows:
        state = memory.get_safety_state(int(guild_id))
        state["enabled"] = bool(enabled)
        
        # Deserialize JSON fields
        if channel_exclusions:
            state["channel_exclusions"] = set(json.loads(channel_exclusions))
        if immunity_roles:
            state["immunity_roles"] = set(json.loads(immunity_roles))
        if module_toggles:
            state["module_toggles"] = json.loads(module_toggles)
        if cooldowns:
            state["cooldowns"] = json.loads(cooldowns)
    
    logger.debug(f"Loaded {len(rows)} safety states")


def save_safety_state(guild_id: int, state: Dict[str, Any]) -> None:
    """Save safety state to database."""
    try:
        db_layer.upsert(
            "honkbot_safety_state",
            {"guild_id": guild_id},
            {
                "enabled": 1 if state.get("enabled", True) else 0,
                "channel_exclusions": json.dumps(list(state.get("channel_exclusions", set()))),
                "immunity_roles": json.dumps(list(state.get("immunity_roles", set()))),
                "module_toggles": json.dumps(state.get("module_toggles", {})),
                "cooldowns": json.dumps(state.get("cooldowns", {})),
            }
        )
    except Exception as e:
        logger.error(f"Error saving safety state: {e}", exc_info=True)


def _load_global_safety_enabled() -> None:
    """Load global safety enabled flag from database."""
    from state import memory
    
    row = db_layer.fetch_one(
        "SELECT state_value FROM honkbot_global_state WHERE state_key = :key",
        {"key": "global_safety_enabled"}
    )
    
    if row:
        memory.set_global_safety_enabled(row[0] == "1")
        logger.debug(f"Loaded global safety enabled: {row[0]}")


def save_global_safety_enabled(enabled: bool) -> None:
    """Save global safety enabled flag to database."""
    try:
        db_layer.upsert(
            "honkbot_global_state",
            {"state_key": "global_safety_enabled"},
            {"state_value": "1" if enabled else "0"}
        )
    except Exception as e:
        logger.error(f"Error saving global safety enabled: {e}", exc_info=True)
