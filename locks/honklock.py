"""
HonkLock — Persistent Goose-Themed Message Lock

THIS MODULE DEFINES USER COMMANDS AND HANDLERS.

HonkLock enforces persistent honkification on a user.
Once locked, ALL of the user’s messages are honkified
until unlocked by an admin or the bot itself

Responsibilities:
- Apply and remove honklocks on users
- Intercept messages from locked users and send the honkified version via webhook
- Delegate actual message transformation to Honkify
- Track lock duration and escalation potential

Commands in this module:
- honk {user}: Apply HonkLock to a user
- unhonk {user}: Remove HonkLock from a user
- honk all: Apply HonkLock to all users (administrators only)
- unhonk all: Remove HonkLock from all users (administrator only)
- honk? {user}: Query HonkLock status

IMPORTANT:
- This module does NOT define honk replacement logic.
- It relies entirely on Honkify for message transformation

Registered explicitly via `register(bot)`.
"""
