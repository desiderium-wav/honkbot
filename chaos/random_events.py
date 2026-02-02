"""
Random Chaos Events — Autonomous Action Definitions

THIS MODULE DEFINES NO COMMANDS.

Defines autonomous chaos events such as:
  - Random honkify or echo on active users
  - Sudden messages or pings
  - Channel takeover events ("channel honkjacked"
  - Media bursts tied to honk escalation 
  - Voice channel disruptions
  - Random drive-by goose interruptions in chat

Takeover Event:
- Triggered when per-channel or per-user honk count crosses a threshold
- Posts "CHANNEL HONKJACKED"
- Emits bursts of HONKs, emojis, and GIFs
- Enforced per-channel cooldow

Events are selected and triggered by the Chaos Decision Loop. Expose callable event functions to the decision loop.

This module does not schedule itself.
"""
