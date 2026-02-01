"""
Honkify — Core Honk Message Transformation System

THIS MODULE DEFINES USER COMMANDS, AUTONOMOUS TRIGGERS, AND CORE LOGIC.

Honkify is the primitive honk transformation system.
It applies honk-based message replacement WITHOUT locking the user.

Responsibilities:
- Transform a single message by replacing words with "honk"
- Detect existing "honk" usage and amplify behavior
- Increment per-user honk counters
- Trigger special responses:
  - Lone honk reply (single-word "honk")
  - Double honk amplification (messages already containing honk)
- Serve as a random chaos event
- Support manual admin-triggered honkify via message reply
- Feed honk counts into escalation systems (takeovers, retaliation)

IMPORTANT DISTINCTION:
- Honkify is stateless and per-message.
- HonkLock enforces persistent honkification and calls Honkify internally.

Commands defined here:
- honkify: Honkify a replied-to message (admin-only)
- honkstats {user}: Show per user honk stats (if no user is defined, the bot will show personal stats for the user sending the command) 
- tophonk: Show honk leaderboard

This module exposes `register(bot)` for command registration.
"""
