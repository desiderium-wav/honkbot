"""
EchoLock — Mocking Message Repetition Commands

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

Commands in this module:
- echo {user}: Apply EchoLock to a user
- unecho {user}: Remove EchoLock from a user
- echo? {user}: Query EchoLock status

Behavior:
- Reposts user messages with exaggerated casing
- Adds randomized mocking commentary and emojis
- May optionally trigger media responses via the media system

This module weaponizes user speech without blocking it.
All commands are registered explicitly via `register(bot)`.
"""
