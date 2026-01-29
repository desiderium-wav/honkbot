"""
honkbot — Autonomous Chaotic Goose Discord Bot

This file is the main entry point for honkbot.

Core concept:
honkbot is a sentient, antagonistic, goose-themed Discord bot inspired by
Untitled Goose Game and Desktop Goose. It behaves as a semi-autonomous menace
with its own internal state, moods, memory, and decision-making loop.

The bot can be interacted with via commands, but it also acts independently:
- Reacts to provocation
- Interrupts conversations
- Deploys chat, media, and voice chat-based chaos
- Retaliates when insulted, pinged, or discussed in chat
- Causes unprompted mayhem

This file should ONLY:
- Initialize the bot
- Register cogs/modules
- Start background tasks

All actual behavior, logic, and chaos is implemented in dedicated modules.
No feature logic should live directly in this file.
"""
