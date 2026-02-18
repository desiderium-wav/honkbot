"""
HonkBot — Autonomous Goose-Themed Discord Bot (Main Entry Point)

This file initializes and runs HonkBot.

Responsibilities of this file ONLY:
- Create the Discord client/bot instance
- Load configuration and environment variables
- Import all system modules
- Explicitly register command suites from modules
- Start autonomous/background systems
- Initialize database schema and load persisted state
- Start the bot

IMPORTANT ARCHITECTURE RULES:
- Modules do NOT self-register.
- All command registration is explicit and occurs here.
- All behavior logic lives in modules, not in this file.

HonkBot is a semi-autonomous, antagonistic goose-inspired bot that:
- Responds to commands
- Acts independently via background decision loops
- Retaliates when provoked
- Disrupts chat, media, and voice channels
- Respects safety controls and administrator overrides (server owner and bot owner only)
"""

from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from chaos import decision_loop
from locks import echolock, honkify, honklock
from media import actions as media_actions
from safety import controls as safety_controls
from db import get_connection

LOG_LEVEL = os.getenv("HONKBOT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("honkbot")
db_conn = None


def _build_intents() -> discord.Intents:
    intents = discord.Intents.all()
    return intents


def _build_bot() -> commands.Bot:
    intents = _build_intents()
    return commands.Bot(command_prefix="~", intents=intents)


def _register_modules(bot: commands.Bot) -> None:
    safety_controls.register(bot)
    media_actions.register(bot)
    honkify.register(bot)
    honklock.register(bot)
    echolock.register(bot)


async def _initialize_persistence() -> None:
    """Initialize database schema and load persisted state."""
    try:
        import db_layer
        from state import persistence as state_persistence
        from media import context_persistence
        from media.context import context_analyzer
        from retaliation import engine as retaliation_engine
        
        # Initialize schema
        logger.info("Initializing database schema...")
        db_layer.initialize_schema()
        
        # Load persisted state
        logger.info("Loading persisted state...")
        state_persistence.load_all_state()
        
        logger.info("Loading context state...")
        context_persistence.load_context_state(context_analyzer)
        
        logger.info("Initializing retaliation engine...")
        retaliation_engine.initialize()
        
        logger.info("Persistence initialization complete")
    except Exception as e:
        logger.error(f"Error initializing persistence: {e}", exc_info=True)


async def _start_background_systems(bot: commands.Bot) -> None:
    await decision_loop.start(bot)


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

        if db_conn is None:
            db_conn = get_connection()
            logger.info("Connected to the database.")
        
        # Initialize persistence
        await _initialize_persistence()
            
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
