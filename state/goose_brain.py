"""
Goose Brain — Core State Machine and Decision Engine

This module defines the Goose Brain:
a persistent internal state machine that governs honkbot's mood,
aggression level, boredom, curiosity, and chaos propensity.

Responsibilities:
- Maintain the goose’s current emotional/behavioral state
- Track recent activity, stimulation, and provocation
- Provide weighted decisions for autonomous actions
- Expose state-based modifiers to other systems (retaliation, chaos, media)

The Goose Brain is authoritative.
All autonomous behavior must consult the Goose Brain before executing.
"""
