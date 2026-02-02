"""
Goose Memory — Internal Memory and Grudge Tracking

THIS MODULE DEFINES NO COMMANDS.

This module stores and manages HonkBot’s memory. 

- Track per-user honk counters
- Track per-channel honk activity
- Track users who have provoked the goose
- Track grudges and maintain provocation history and decay
- Maintain decay logic for honk counts
- Store recent honkified messages
- Maintain escalation thresholds (e.g., takeover eligibility)
- Track recent actions taken (anti-repetition)
- Maintain learned context keywords and topics

Memory supports both in-memory and persistent storage.
This module contains logic only and performs no Discord actions.
"""
