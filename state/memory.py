"""
Goose Memory — Internal Memory and Context Tracking

This module manages honkbot’s internal memory, including:
- Users who have provoked the goose
- Recent targets and victims
- Recently used actions (to prevent repetition)
- Learned context keywords and topics
- Cooldowns and grudges

Memory may be short-term (session-based) or persistent (stored to disk).

This system enables the goose to appear aware, reactive, and vindictive.
"""
