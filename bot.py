"""
HonkBot — Autonomous Goose-Themed Discord Bot (Main Entry Point)

This file initializes and runs HonkBot.

Responsibilities of this file ONLY:
- Create the Discord client/bot instance
- Load configuration and environment variables
- Import all system modules
- Explicitly register command suites from modules
- Start autonomous/background systems
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


LOG_LEVEL = os.getenv("HONKBOT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("honkbot")


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
