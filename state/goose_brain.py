"""
Goose Brain — Core State Machine and Decision Authority

THIS MODULE DEFINES NO COMMANDS.

This module implements HonkBot’s internal state machine.
It is the authoritative source of the goose’s “mind.”

Responsibilities:
- Track mood, aggression, boredom, curiosity, and chaos level
- Maintain state transitions over time
- Expose read-only state to other systems
- Provide weighted decision modifiers for autonomous actions

All autonomous systems MUST consult the Goose Brain before acting.
No Discord API calls should occur in this module.
"""