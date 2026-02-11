"""
Media Context Analyzer — Conversation Understanding Logic

THIS MODULE DEFINES NO COMMANDS.

Responsibilities:
- Monitor recent conversation text
- Detect topics and keywords
- Learn new keywords automatically
- Map keywords to media categories

This module provides context intelligence to other systems.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

# Basic stopwords to avoid learning meaningless terms.
_STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "for", "to",
    "of", "in", "on", "at", "by", "with", "from", "as", "is", "are", "was",
    "were", "be", "been", "being", "it", "this", "that", "these", "those",
    "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "hers", "our", "their", "not", "no", "yes", "do",
    "does", "did", "doing", "have", "has", "had",
}

# Seed mapping of keywords to high-level topics.
# Extend this map to add domain-specific categories.
DEFAULT_KEYWORD_TOPICS: Dict[str, str] = {
    "music": "audio",
    "song": "audio",
    "playlist": "audio",
    "podcast": "audio",
    "video": "video",
    "clip": "video",
    "movie": "video",
    "show": "video",
    "image": "visual",
    "photo": "visual",
    "picture": "visual",
    "meme": "visual",
    "gif": "visual",
    "art": "visual",
    "game": "gaming",
    "gaming": "gaming",
    "stream": "gaming",
    "news": "news",
    "update": "news",
    "announcement": "news",
    "release": "news",
}

@dataclass
class MessageEvent:
    timestamp: datetime
    author: str
    content: str

@dataclass
class ContextSnapshot:
    last_updated: datetime
    recent_messages: List[MessageEvent]
    top_keywords: List[Tuple[str, int]]
    inferred_topics: List[Tuple[str, float]]
    learned_keywords: List[str]

@dataclass
class ContextAnalyzer:
    max_history: int = 50
    min_keyword_length: int = 3
    min_keyword_frequency: int = 2
    keyword_topics: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYWORD_TOPICS))
    learned_keywords: Set[str] = field(default_factory=set)

    _history: Deque[MessageEvent] = field(default_factory=deque, init=False)
    _keyword_counts: Counter = field(default_factory=Counter, init=False)
    _last_updated: Optional[datetime] = field(default=None, init=False)

    def add_message(self, author: str, content: str, timestamp: Optional[datetime] = None) -> None:
        """Add a message to the rolling history and update keyword/topic signals."""
        if not content:
            return

        timestamp = timestamp or datetime.utcnow()
        event = MessageEvent(timestamp=timestamp, author=author, content=content)
        self._history.append(event)
        self._last_updated = timestamp

        if len(self._history) > self.max_history:
            removed = self._history.popleft()
            self._decrement_keywords(removed.content)

        self._increment_keywords(content)

    def _tokenize(self, text: str) -> Iterable[str]:
        for raw in text.lower().split():
            token = "".join(ch for ch in raw if ch.isalnum())
            if len(token) < self.min_keyword_length:
                continue
            if token in _STOPWORDS:
                continue
            yield token

    def _increment_keywords(self, text: str) -> None:
        tokens = list(self._tokenize(text))
        self._keyword_counts.update(tokens)
        self._learn_keywords(tokens)

    def _decrement_keywords(self, text: str) -> None:
        tokens = list(self._tokenize(text))
        for token in tokens:
            if self._keyword_counts[token] > 1:
                self._keyword_counts[token] -= 1
            elif token in self._keyword_counts:
                del self._keyword_counts[token]

    def _learn_keywords(self, tokens: Iterable[str]) -> None:
        for token in tokens:
            if token in self.keyword_topics:
                continue
            if self._keyword_counts[token] >= self.min_keyword_frequency:
                self.learned_keywords.add(token)

    def infer_topics(self) -> List[Tuple[str, float]]:
        """Infer topics based on known and learned keywords."""
        if not self._keyword_counts:
            return []

        topic_counts: Counter = Counter()
        total = sum(self._keyword_counts.values())

        for keyword, count in self._keyword_counts.items():
            topic = self.keyword_topics.get(keyword)
            if topic:
                topic_counts[topic] += count
            elif keyword in self.learned_keywords:
                topic_counts["misc"] += count

        if not topic_counts:
            return []

        return sorted(
            ((topic, count / total) for topic, count in topic_counts.items()),
            key=lambda item: item[1],
            reverse=True,
        )

    def summarize_context(self, top_n_keywords: int = 10, recent_limit: int = 5) -> ContextSnapshot:
        """Return a summary of the current conversation context."""
        recent_messages = list(self._history)[-recent_limit:]
        top_keywords = self._keyword_counts.most_common(top_n_keywords)
        inferred_topics = self.infer_topics()

        return ContextSnapshot(
            last_updated=self._last_updated or datetime.utcnow(),
            recent_messages=recent_messages,
            top_keywords=top_keywords,
            inferred_topics=inferred_topics,
            learned_keywords=sorted(self.learned_keywords),
        )

    def clear(self) -> None:
        """Reset all stored context."""
        self._history.clear()
        self._keyword_counts.clear()
        self.learned_keywords.clear()
        self._last_updated = None


# Shared singleton for convenience; other modules can import this.
context_analyzer = ContextAnalyzer()
