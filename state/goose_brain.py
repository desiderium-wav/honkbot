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

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Iterable, Mapping
import time


class Mood(str, Enum):
    SERENE = "serene"
    ALERT = "alert"
    AGITATED = "agitated"
    FEROCIOUS = "ferocious"
    CHAOTIC = "chaotic"


class Intent(str, Enum):
    OBSERVE = "observe"
    WANDER = "wander"
    HONK = "honk"
    PECK = "peck"
    CHASE = "chase"
    INVESTIGATE = "investigate"
    RETREAT = "retreat"


DEFAULT_DECAY_SECONDS = 300.0
DEFAULT_DELTA_SECONDS = 30.0
DEFAULT_STATE = None


@dataclass(frozen=True)
class GooseState:
    mood: Mood
    aggression: float
    boredom: float
    curiosity: float
    chaos: float
    last_updated: float


@dataclass(frozen=True)
class DecisionWeights:
    modifiers: Dict[Intent, float]

    def normalized(self) -> Dict[Intent, float]:
        total = sum(value for value in self.modifiers.values() if value > 0.0)
        if total <= 0:
            return {intent: 0.0 for intent in self.modifiers}
        return {intent: max(0.0, value) / total for intent, value in self.modifiers.items()}


_state: GooseState | None = DEFAULT_STATE


EVENT_EFFECTS: Mapping[str, Dict[str, float]] = {
    "honked_at": {"aggression": 0.2, "chaos": 0.1, "boredom": -0.15},
    "petted": {"aggression": -0.2, "curiosity": 0.05, "boredom": -0.1},
    "ignored": {"boredom": 0.2, "curiosity": -0.05},
    "food_offered": {"curiosity": 0.25, "aggression": -0.1},
    "chased": {"aggression": 0.35, "chaos": 0.2},
    "loud_noise": {"aggression": 0.15, "curiosity": 0.1, "chaos": 0.15},
    "praised": {"aggression": -0.1, "boredom": -0.05, "curiosity": 0.1},
}


MOOD_THRESHOLDS = (
    (Mood.SERENE, 0.0, 0.25),
    (Mood.ALERT, 0.25, 0.45),
    (Mood.AGITATED, 0.45, 0.65),
    (Mood.FEROCIOUS, 0.65, 0.85),
    (Mood.CHAOTIC, 0.85, 1.01),
)


INTENT_BASE_WEIGHTS: Dict[Intent, float] = {
    Intent.OBSERVE: 0.2,
    Intent.WANDER: 0.2,
    Intent.HONK: 0.2,
    Intent.PECK: 0.15,
    Intent.CHASE: 0.1,
    Intent.INVESTIGATE: 0.1,
    Intent.RETREAT: 0.05,
}


INTENT_DRIVERS: Dict[Intent, Dict[str, float]] = {
    Intent.OBSERVE: {"curiosity": 0.2, "boredom": -0.1},
    Intent.WANDER: {"boredom": 0.3, "curiosity": 0.05},
    Intent.HONK: {"aggression": 0.35, "chaos": 0.1},
    Intent.PECK: {"aggression": 0.25, "curiosity": 0.1},
    Intent.CHASE: {"aggression": 0.4, "chaos": 0.2},
    Intent.INVESTIGATE: {"curiosity": 0.35},
    Intent.RETREAT: {"aggression": -0.25, "chaos": 0.05},
}


MOOD_INTENT_BONUS: Dict[Mood, Dict[Intent, float]] = {
    Mood.SERENE: {Intent.OBSERVE: 0.1, Intent.RETREAT: 0.05},
    Mood.ALERT: {Intent.INVESTIGATE: 0.08},
    Mood.AGITATED: {Intent.HONK: 0.1, Intent.PECK: 0.05},
    Mood.FEROCIOUS: {Intent.CHASE: 0.15, Intent.HONK: 0.08},
    Mood.CHAOTIC: {Intent.CHASE: 0.1, Intent.HONK: 0.1, Intent.WANDER: 0.05},
}


DECAY_RATES = {
    "aggression": 0.015,
    "boredom": -0.01,
    "curiosity": -0.01,
    "chaos": 0.01,
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _resolve_mood(aggression: float, chaos: float) -> Mood:
    intensity = _clamp((aggression * 0.7) + (chaos * 0.3))
    for mood, low, high in MOOD_THRESHOLDS:
        if low <= intensity < high:
            return mood
    return Mood.CHAOTIC


def _ensure_state(now: float | None = None) -> GooseState:
    global _state
    if _state is None:
        _state = GooseState(
            mood=Mood.SERENE,
            aggression=0.2,
            boredom=0.2,
            curiosity=0.3,
            chaos=0.1,
            last_updated=now or time.time(),
        )
    return _state


def get_state(now: float | None = None) -> GooseState:
    state = _ensure_state(now)
    return state


def _apply_decay(state: GooseState, now: float, decay_seconds: float) -> GooseState:
    elapsed = max(0.0, now - state.last_updated)
    if decay_seconds <= 0:
        return state
    factor = min(1.0, elapsed / decay_seconds)
    aggression = _clamp(state.aggression - (DECAY_RATES["aggression"] * factor))
    boredom = _clamp(state.boredom + (DECAY_RATES["boredom"] * factor))
    curiosity = _clamp(state.curiosity + (DECAY_RATES["curiosity"] * factor))
    chaos = _clamp(state.chaos + (DECAY_RATES["chaos"] * factor))
    mood = _resolve_mood(aggression, chaos)
    return replace(
        state,
        aggression=aggression,
        boredom=boredom,
        curiosity=curiosity,
        chaos=chaos,
        mood=mood,
        last_updated=now,
    )


def update_state(
    event: str,
    intensity: float = 1.0,
    now: float | None = None,
    decay_seconds: float = DEFAULT_DECAY_SECONDS,
) -> GooseState:
    global _state
    timestamp = now or time.time()
    state = _apply_decay(_ensure_state(timestamp), timestamp, decay_seconds)

    adjustments = EVENT_EFFECTS.get(event, {})
    aggression = state.aggression + adjustments.get("aggression", 0.0) * intensity
    boredom = state.boredom + adjustments.get("boredom", 0.0) * intensity
    curiosity = state.curiosity + adjustments.get("curiosity", 0.0) * intensity
    chaos = state.chaos + adjustments.get("chaos", 0.0) * intensity

    aggression = _clamp(aggression)
    boredom = _clamp(boredom)
    curiosity = _clamp(curiosity)
    chaos = _clamp(chaos)

    mood = _resolve_mood(aggression, chaos)
    _state = GooseState(
        mood=mood,
        aggression=aggression,
        boredom=boredom,
        curiosity=curiosity,
        chaos=chaos,
        last_updated=timestamp,
    )
    return _state


def tick(now: float | None = None, decay_seconds: float = DEFAULT_DECAY_SECONDS) -> GooseState:
    global _state
    timestamp = now or time.time()
    _state = _apply_decay(_ensure_state(timestamp), timestamp, decay_seconds)
    return _state


def get_decision_weights(state: GooseState | None = None) -> DecisionWeights:
    active = state or _ensure_state()
    weights: Dict[Intent, float] = {intent: base for intent, base in INTENT_BASE_WEIGHTS.items()}

    drivers = {
        "aggression": active.aggression,
        "boredom": active.boredom,
        "curiosity": active.curiosity,
        "chaos": active.chaos,
    }

    for intent, modifiers in INTENT_DRIVERS.items():
        for key, value in modifiers.items():
            weights[intent] = weights.get(intent, 0.0) + (drivers.get(key, 0.0) * value)

    for intent, bonus in MOOD_INTENT_BONUS.get(active.mood, {}).items():
        weights[intent] = weights.get(intent, 0.0) + bonus

    return DecisionWeights(weights)


def get_intent(state: GooseState | None = None) -> Intent:
    weights = get_decision_weights(state).normalized()
    return max(weights, key=weights.get)


def get_intent_breakdown(state: GooseState | None = None) -> Dict[str, float]:
    weights = get_decision_weights(state).normalized()
    return {intent.value: score for intent, score in weights.items()}


def set_state(
    mood: Mood | None = None,
    aggression: float | None = None,
    boredom: float | None = None,
    curiosity: float | None = None,
    chaos: float | None = None,
    now: float | None = None,
) -> GooseState:
    global _state
    state = _ensure_state(now or time.time())
    aggression = _clamp(aggression if aggression is not None else state.aggression)
    boredom = _clamp(boredom if boredom is not None else state.boredom)
    curiosity = _clamp(curiosity if curiosity is not None else state.curiosity)
    chaos = _clamp(chaos if chaos is not None else state.chaos)
    resolved_mood = mood or _resolve_mood(aggression, chaos)
    _state = GooseState(
        mood=resolved_mood,
        aggression=aggression,
        boredom=boredom,
        curiosity=curiosity,
        chaos=chaos,
        last_updated=now or time.time(),
    )
    return _state


def list_known_events() -> Iterable[str]:
    return EVENT_EFFECTS.keys()