"""
Echo — Mocking Message Repetition Commands

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

Commands in this module:
- echo {user}: Apply Echo to a user
- unecho {user}: Remove Echo from a user

Behavior:
- Replies to user messages by reposting the original message with exaggerated casing
- Adds randomized mocking commentary and emojis
- May also trigger media responses via the media system

This module weaponizes user speech without blocking it.
All commands are registered explicitly via `register(bot)`.
"""
