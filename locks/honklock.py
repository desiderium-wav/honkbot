"""
HonkLock — Goose-Themed Message Corruption Commands

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

Commands in this module:
- honk: Apply HonkLock to a user
- unhonk: Remove HonkLock from a user
- honk all: Apply HonkLock to all users (administrators only)
- honk? {user}: Query HonkLock status

Behavior:
- Rewrites user messages by replacing nouns or key words with "honk"
- Variants may include capitalization, repetition, or absurd phrasing
- Deletes original messages and resends honklocked version via webhook
- Copies honklocked user's display name and avatar to make the webhook look like it's coming from the honklocked user   

This module must:
- Define command handler functions
- Define message transformation helpers
- Expose a `register(bot)` function for bot.py to call
"""
