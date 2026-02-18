"""
HonkBot — Main entry (updated: wait briefly for DB init to avoid decision loop starting
and immediately hitting persistence while DB connection is still being negotiated)
"""
from __future__ import annotations

import logging
import os
import asyncio
from functools import partial

import discord
from discord.ext import commands
from dotenv import load_dotenv

from chaos import decision_loop
from locks import echolock, honkify, honklock
from media import actions as media_actions
from safety import controls as safety_controls
from db import get_connection, set_cached_connection

LOG_LEVEL = os.getenv("HONKBOT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("honkbot")
db_conn = None


def _build_intents() -> discord.Intents:
    intents = discord.Intents.all()
    return intents


def _build_bot() -> commands.Bot:
    intents = _build_intents()
    return commands.Bot(command_prefix="-", intents=intents)


def _register_modules(bot: commands.Bot) -> None:
    safety_controls.register(bot)
    media_actions.register(bot)
    honkify.register(bot)
    honklock.register(bot)
    echolock.register(bot)


def _persistent_init_sync() -> None:
    try:
        import db_layer
        from state import persistence as state_persistence
        from media import context_persistence
        from media.context import context_analyzer
        from retaliation import engine as retaliation_engine

        logger.info("Initializing database schema (sync)...")
        db_layer.initialize_schema()

        logger.info("Loading persisted state (sync)...")
        state_persistence.load_all_state()

        logger.info("Loading context state (sync)...")
        context_persistence.load_context_state(context_analyzer)

        logger.info("Initializing retaliation engine (sync)...")
        retaliation_engine.initialize()

        logger.info("Persistence initialization complete (sync).")
    except Exception as e:
        logger.exception("Error initializing persistence (sync): %s", e)


async def _start_background_systems(bot: commands.Bot) -> None:
    from utils import persistence_tasks

    await decision_loop.start(bot)

    global db_conn
    if db_conn:
        await persistence_tasks.start()
    else:
        logger.info("Skipping persistence tasks because no DB connection is available.")


async def _attempt_db_connect_and_init(retries: int = 1, retry_delay: float = 2.0) -> None:
    global db_conn
    loop = asyncio.get_running_loop()
    try:
        logger.info("Attempting database connection in background (non-blocking executor)...")
        conn = await loop.run_in_executor(None, partial(get_connection, retries, retry_delay))
        if conn:
            # Cache the connection in both modules: bot and db
            db_conn = conn
            try:
                # also set cached conn inside db module for fast returns
                set_cached_connection(conn)
            except Exception:
                logger.debug("Failed to call set_cached_connection in db module (non-fatal).")
            logger.info("Connected to the database (background). Running sync persistence init in executor...")
            await loop.run_in_executor(None, _persistent_init_sync)
        else:
            logger.info("Database connection not configured or unavailable; skipping persistence init.")
    except Exception as e:
        logger.exception("Background DB connect/init failed: %s", e)


def main() -> None:
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN environment variable.")

    bot = _build_bot()
    _register_modules(bot)

    @bot.event
    async def on_ready() -> None:
        global db_conn

        # Start background DB connect+init, but wait briefly (timeout) for it to finish
        # so we don't immediately start decision_loop which writes persistence.
        bg_task = asyncio.create_task(_attempt_db_connect_and_init(retries=3, retry_delay=2.0))
        try:
            await asyncio.wait_for(bg_task, timeout=5.0)
            logger.info("Background DB init task completed within timeout.")
        except asyncio.TimeoutError:
            logger.info("DB init did not complete within timeout; proceeding without persistence for now.")
        except Exception:
            logger.exception("Background DB init task raised an error.")

        logger.info("HonkBot connected as %s", bot.user)
        await _start_background_systems(bot)

        try:
            synced = await bot.tree.sync()
            logger.info("Synced %s application commands.", len(synced))
        except Exception:
            logger.exception("Failed to sync application commands.")

    bot.run(token)


if __name__ == "__main__":
    main()
