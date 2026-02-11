"""
HonkBot Logging — Action and Audit Logging

THIS MODULE DEFINES NO COMMANDS.

Responsibilities:
- Log autonomous actions
- Log retaliations and punishments
- Log admin control changes
- Log errors and unexpected behavior

Used for debugging, audits, and accountability.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

DEFAULT_LOGGER_NAME = "honkbot.audit"

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _json_default(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return "<unserializable>"

def _merge_context(base: Optional[Mapping[str, Any]], extra: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if base:
        merged.update(base)
    if extra:
        merged.update(extra)
    return merged

@dataclass
class LogContext:
    """Reusable structured context for audit logs."""
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    command: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        base = {
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "command": self.command,
        }
        return _merge_context(base, self.extra)

class StructuredFormatter(logging.Formatter):
    """Format log records as JSON strings with structured fields."""
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": _utc_now_iso(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "data"):
            payload["data"] = record.data
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_json_default)

def get_audit_logger(name: str = DEFAULT_LOGGER_NAME) -> logging.Logger:
    """Get or create the structured audit logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    logger.addHandler(handler)
    logger.propagate = False
    return logger

def _log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    context: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
    exc_info: Optional[BaseException] = None,
) -> None:
    payload = _merge_context(context, extra)
    logger.log(level, message, extra={"event": event, "data": payload}, exc_info=exc_info)

def log_action(
    message: str,
    *,
    context: Optional[LogContext | Mapping[str, Any]] = None,
    action: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    **extra: Any,
) -> None:
    """Log an autonomous action."""
    resolved_logger = logger or get_audit_logger()
    ctx = context.as_dict() if isinstance(context, LogContext) else (context or {})
    if action:
        extra["action"] = action
    _log_event(resolved_logger, logging.INFO, "action", message, ctx, extra or None)

def log_escalation(
    message: str,
    *,
    context: Optional[LogContext | Mapping[str, Any]] = None,
    escalation: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    **extra: Any,
) -> None:
    """Log a retaliation, punishment, or escalation."""
    resolved_logger = logger or get_audit_logger()
    ctx = context.as_dict() if isinstance(context, LogContext) else (context or {})
    if escalation:
        extra["escalation"] = escalation
    _log_event(resolved_logger, logging.WARNING, "escalation", message, ctx, extra or None)

def log_admin_change(
    message: str,
    *,
    context: Optional[LogContext | Mapping[str, Any]] = None,
    change: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    **extra: Any,
) -> None:
    """Log an admin control change."""
    resolved_logger = logger or get_audit_logger()
    ctx = context.as_dict() if isinstance(context, LogContext) else (context or {})
    if change:
        extra["change"] = change
    _log_event(resolved_logger, logging.INFO, "admin_change", message, ctx, extra or None)

def log_error(
    message: str,
    *,
    context: Optional[LogContext | Mapping[str, Any]] = None,
    error: Optional[BaseException] = None,
    logger: Optional[logging.Logger] = None,
    **extra: Any,
) -> None:
    """Log an error or unexpected behavior."""
    resolved_logger = logger or get_audit_logger()
    ctx = context.as_dict() if isinstance(context, LogContext) else (context or {})
    if error:
        extra["error"] = repr(error)
    _log_event(resolved_logger, logging.ERROR, "error", message, ctx, extra or None, exc_info=error)

def log_batch(
    event: str,
    entries: Iterable[Mapping[str, Any]],
    *,
    message: Optional[str] = None,
    level: int = logging.INFO,
    logger: Optional[logging.Logger] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> None:
    """Log multiple structured entries under the same event name."""
    resolved_logger = logger or get_audit_logger()
    for entry in entries:
        _log_event(
            resolved_logger,
            level,
            event,
            message or event,
            context,
            entry,
        )
