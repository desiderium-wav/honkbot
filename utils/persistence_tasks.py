"""
Persistence Background Tasks — Periodic Saving of State

This module defines background tasks for periodically persisting state to the database.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
SAVE_INTERVAL_SECONDS = 300  # 5 minutes


async def _periodic_save_loop() -> None:
    """
    Periodic loop to save context snapshots and other state to database.
    """
    try:
        while True:
            await asyncio.sleep(SAVE_INTERVAL_SECONDS)
            
            try:
                # Save context snapshot
                from media.context import context_analyzer
                context_analyzer.persist_snapshot()
                logger.debug("Periodic context snapshot saved")
            except Exception as e:
                logger.error(f"Error saving context snapshot: {e}", exc_info=True)
            
            # Future: add other periodic persistence tasks here
            
    except asyncio.CancelledError:
        logger.info("Periodic save loop cancelled")
        raise


async def start() -> None:
    """Start the periodic save background task."""
    global _task
    if _task and not _task.done():
        return
    
    _task = asyncio.create_task(_periodic_save_loop())
    logger.info("Periodic save task started")


async def stop() -> None:
    """Stop the periodic save background task."""
    global _task
    if not _task:
        return
    
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    logger.info("Periodic save task stopped")
