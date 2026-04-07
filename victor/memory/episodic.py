"""
EpisodicMemory — The first layer of Victor's three-tier memory system.

Episodic memory stores raw events: conversations, actions, observations,
and interactions with their timestamps, participants, and emotional weight.
It answers the question: **what happened?**
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Optional


@dataclass
class Episode:
    """
    A single episodic record.

    Attributes
    ----------
    id:
        Unique identifier for this episode.
    timestamp:
        UTC datetime when the event occurred.
    event_type:
        Semantic category of the event (e.g. ``"conversation"``,
        ``"decision"``, ``"observation"``, ``"breakthrough"``, ``"failure"``).
    content:
        Free-text description or transcript of the event.
    participants:
        Identifiers of all agents/humans involved.
    emotional_weight:
        Normalised emotional significance in the range ``[-1.0, 1.0]``.
        Negative values represent distress/loss; positive values represent
        joy/gain.  ``0.0`` is neutral.
    tags:
        Arbitrary labels for later retrieval and pattern detection.
    metadata:
        Extensible key-value store for domain-specific fields.
    """

    id: str
    timestamp: str  # ISO-8601 UTC string
    event_type: str
    content: str
    participants: list[str]
    emotional_weight: float  # [-1.0, 1.0]
    tags: list[str]
    metadata: dict

    @classmethod
    def create(
        cls,
        event_type: str,
        content: str,
        participants: Optional[list[str]] = None,
        emotional_weight: float = 0.0,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        timestamp: Optional[datetime] = None,
    ) -> "Episode":
        if not -1.0 <= emotional_weight <= 1.0:
            raise ValueError(
                f"emotional_weight must be in [-1.0, 1.0], got {emotional_weight}"
            )
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        return cls(
            id=str(uuid.uuid4()),
            timestamp=ts,
            event_type=event_type,
            content=content,
            participants=list(participants or []),
            emotional_weight=emotional_weight,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "content": self.content,
            "participants": self.participants,
            "emotional_weight": self.emotional_weight,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            event_type=data["event_type"],
            content=data["content"],
            participants=data.get("participants", []),
            emotional_weight=data.get("emotional_weight", 0.0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class EpisodicMemory:
    """
    Ordered, queryable store of :class:`Episode` records.

    Episodes are appended in chronological order and can be retrieved by
    type, participant, tag, or time range.
    """

    def __init__(self) -> None:
        self._episodes: list[Episode] = []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, episode: Episode) -> None:
        """Append an episode to memory."""
        self._episodes.append(episode)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all(self) -> list[Episode]:
        """Return all episodes in chronological order."""
        return list(self._episodes)

    def by_type(self, event_type: str) -> list[Episode]:
        """Return episodes matching *event_type*."""
        return [e for e in self._episodes if e.event_type == event_type]

    def by_participant(self, participant_id: str) -> list[Episode]:
        """Return episodes involving *participant_id*."""
        return [e for e in self._episodes if participant_id in e.participants]

    def by_tag(self, tag: str) -> list[Episode]:
        """Return episodes carrying *tag*."""
        return [e for e in self._episodes if tag in e.tags]

    def high_weight(self, threshold: float = 0.5) -> list[Episode]:
        """Return episodes whose absolute emotional weight exceeds *threshold*."""
        return [e for e in self._episodes if abs(e.emotional_weight) >= threshold]

    def get(self, episode_id: str) -> Optional[Episode]:
        """Return the episode with the given id, or ``None``."""
        for e in self._episodes:
            if e.id == episode_id:
                return e
        return None

    def __len__(self) -> int:
        return len(self._episodes)

    def __iter__(self) -> Iterator[Episode]:
        return iter(self._episodes)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"episodes": [e.to_dict() for e in self._episodes]}

    @classmethod
    def from_dict(cls, data: dict) -> "EpisodicMemory":
        mem = cls()
        for raw in data.get("episodes", []):
            mem.record(Episode.from_dict(raw))
        return mem
