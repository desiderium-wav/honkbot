"""
Voice Behavior — Voice Channel Chaos System

THIS MODULE DEFINES AUTONOMOUS BEHAVIOR AND OPTIONAL HELPER COMMANDS.

Autonomous behavior:
- Randomly join active voice channels silently
- Leave after a random duration
- Join inactive channels and idle
- Move a random user, then immediately leave

Optional admin/helper commands:
- Force the goose to leave voice
- Temporarily disable voice chaos

Voice actions are semi-rare, timed, and state-dependent.
"""
