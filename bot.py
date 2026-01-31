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