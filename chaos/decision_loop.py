"""
Chaos Decision Loop — Autonomous Goose Behavior Scheduler

THIS MODULE DEFINES BACKGROUND TASKS ONLY.

Responsibilities:
- Periodically evaluate server activity
- Consult Goose Brain and Memory
- Increase chaos probability based on honk density
- Trigger honkify events, takeovers, and media bursts
- Respect cooldowns and safety control
- Roll weighted probabilities for chaos events
- Trigger random actions via other systems

This loop gives HonkBot its “mind of its own.”
No commands are defined here.
"""
