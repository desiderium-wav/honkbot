from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from locks import honkify
from state import memory
from utils.text import safe_truncate

WEBHOOK_NAME = "HonkLock"
MAX_REPLY_LENGTH = 1900

# ...
def register(bot: commands.Bot) -> None:
    @bot.command(name="honk")
    @commands.has_permissions(administrator=True)
    async def honk_cmd(ctx: commands.Context, *, target: Optional[str] = None) -> None:
        # ...
    # ...
    @bot.listen("on_message")
    async def honklock_listener(message: discord.Message) -> None:
        if honkify._should_ignore_message(message, bot):
            return
        if not message.content:
            return
        if not memory.is_honklocked(message.author.id):
            return
        # ...
