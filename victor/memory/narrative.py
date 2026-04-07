"""
NarrativeMemory — The second layer of Victor's three-tier memory system.

Narrative memory transforms raw episodes into life-arc structure.
It stores *meaning*, not mere facts: turning points, wounds and
breakthroughs, repeated patterns, promises and vows, origin stories,
unresolved threads, and the current chapter of the human's life.

It answers the question: **why did it matter?**
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class NarrativeEvent:
    """
    A semantically enriched record derived from one or more episodes.

    Attributes
    ----------
    id:
        Unique identifier.
    episode_ids:
        Source episode IDs that produced this narrative event.
    is_turning_point:
        ``True`` if this event marks a significant inflection in the
        human's life arc.
    wound_or_breakthrough:
        ``"wound"`` — a loss, failure, or trauma that must be accounted
        for. ``"breakthrough"`` — a gain, realisation, or transformation.
        ``None`` if neither applies.
    meaning:
        A concise human-readable sentence capturing *why* this mattered.
    implications:
        Forward-looking inferences: what this event implies for future
        choices, relationships, or goals.
    pattern_tags:
        Recurring behavioural or emotional patterns this event exemplifies
        (e.g. ``"avoidance"``, ``"over-commitment"``, ``"creative_surge"``).
    life_arc_chapter:
        Identifier of the life-arc chapter this event belongs to.
    promises_or_vows:
        Any explicit commitments made during or because of this event.
    timestamp:
        ISO-8601 UTC string of when the narrative record was created.
    """

    id: str
    episode_ids: list[str]
    is_turning_point: bool
    wound_or_breakthrough: Optional[str]  # "wound" | "breakthrough" | None
    meaning: str
    implications: list[str]
    pattern_tags: list[str]
    life_arc_chapter: str
    promises_or_vows: list[str]
    timestamp: str  # ISO-8601 UTC

    @classmethod
    def create(
        cls,
        episode_ids: list[str],
        meaning: str,
        life_arc_chapter: str,
        is_turning_point: bool = False,
        wound_or_breakthrough: Optional[str] = None,
        implications: Optional[list[str]] = None,
        pattern_tags: Optional[list[str]] = None,
        promises_or_vows: Optional[list[str]] = None,
    ) -> "NarrativeEvent":
        if wound_or_breakthrough not in (None, "wound", "breakthrough"):
            raise ValueError(
                "wound_or_breakthrough must be 'wound', 'breakthrough', or None; "
                f"got {wound_or_breakthrough!r}"
            )
        return cls(
            id=str(uuid.uuid4()),
            episode_ids=list(episode_ids),
            is_turning_point=is_turning_point,
            wound_or_breakthrough=wound_or_breakthrough,
            meaning=meaning,
            implications=list(implications or []),
            pattern_tags=list(pattern_tags or []),
            life_arc_chapter=life_arc_chapter,
            promises_or_vows=list(promises_or_vows or []),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "episode_ids": self.episode_ids,
            "is_turning_point": self.is_turning_point,
            "wound_or_breakthrough": self.wound_or_breakthrough,
            "meaning": self.meaning,
            "implications": self.implications,
            "pattern_tags": self.pattern_tags,
            "life_arc_chapter": self.life_arc_chapter,
            "promises_or_vows": self.promises_or_vows,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NarrativeEvent":
        return cls(
            id=data["id"],
            episode_ids=data.get("episode_ids", []),
            is_turning_point=data.get("is_turning_point", False),
            wound_or_breakthrough=data.get("wound_or_breakthrough"),
            meaning=data["meaning"],
            implications=data.get("implications", []),
            pattern_tags=data.get("pattern_tags", []),
            life_arc_chapter=data.get("life_arc_chapter", ""),
            promises_or_vows=data.get("promises_or_vows", []),
            timestamp=data.get("timestamp", ""),
        )


class NarrativeMemory:
    """
    Store of :class:`NarrativeEvent` records indexed for life-arc queries.
    """

    def __init__(self) -> None:
        self._events: list[NarrativeEvent] = []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, event: NarrativeEvent) -> None:
        """Append a narrative event."""
        self._events.append(event)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all(self) -> list[NarrativeEvent]:
        return list(self._events)

    def turning_points(self) -> list[NarrativeEvent]:
        return [e for e in self._events if e.is_turning_point]

    def wounds(self) -> list[NarrativeEvent]:
        return [e for e in self._events if e.wound_or_breakthrough == "wound"]

    def breakthroughs(self) -> list[NarrativeEvent]:
        return [e for e in self._events if e.wound_or_breakthrough == "breakthrough"]

    def by_chapter(self, chapter: str) -> list[NarrativeEvent]:
        return [e for e in self._events if e.life_arc_chapter == chapter]

    def by_pattern(self, pattern_tag: str) -> list[NarrativeEvent]:
        return [e for e in self._events if pattern_tag in e.pattern_tags]

    def all_promises(self) -> list[str]:
        """Return all promises/vows recorded across all narrative events."""
        promises: list[str] = []
        for event in self._events:
            promises.extend(event.promises_or_vows)
        return promises

    def unresolved_threads(self) -> list[NarrativeEvent]:
        """
        Return narrative events that carry unresolved implications
        (i.e., the implications list is non-empty).
        """
        return [e for e in self._events if e.implications]

    def get(self, event_id: str) -> Optional[NarrativeEvent]:
        for e in self._events:
            if e.id == event_id:
                return e
        return None

    def __len__(self) -> int:
        return len(self._events)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"events": [e.to_dict() for e in self._events]}

    @classmethod
    def from_dict(cls, data: dict) -> "NarrativeMemory":
        mem = cls()
        for raw in data.get("events", []):
            mem.record(NarrativeEvent.from_dict(raw))
        return mem
