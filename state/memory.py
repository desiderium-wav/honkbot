"""
Goose Memory — Internal Memory and Grudge Tracking

THIS MODULE DEFINES NO COMMANDS.

This module stores and manages HonkBot’s memory, including:
- Users who have provoked the goose
- Provocation history and decay
- Recent actions taken (anti-repetition)
- Learned context keywords and topics
- Temporary grudges and cooldowns

Memory supports both in-memory and persistent storage.
This module contains logic only and performs no Discord actions.
"""