"""
NarrativeEngine — Transforms raw episodic events into life-arc structure.

The engine processes :class:`~victor.memory.episodic.Episode` objects and
produces :class:`~victor.memory.narrative.NarrativeEvent` records, organising
them into named life-arc chapters.  This is where raw experience becomes
*meaning*.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from victor.memory.episodic import Episode
from victor.memory.narrative import NarrativeEvent, NarrativeMemory


@dataclass
class LifeArcChapter:
    """
    A named period in the human's life arc.

    Attributes
    ----------
    id:
        Unique identifier.
    name:
        Human-readable chapter name (e.g. ``"The Founding Years"``).
    description:
        Brief synopsis of what this chapter represents.
    started_at:
        ISO-8601 UTC when this chapter began.
    ended_at:
        ISO-8601 UTC when this chapter closed, or ``None`` if current.
    themes:
        Recurring themes present in this chapter.
    """

    id: str
    name: str
    description: str
    started_at: str  # ISO-8601 UTC
    ended_at: Optional[str]  # ISO-8601 UTC or None
    themes: list[str]

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        themes: Optional[list[str]] = None,
        started_at: Optional[datetime] = None,
    ) -> "LifeArcChapter":
        ts = (started_at or datetime.now(timezone.utc)).isoformat()
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            started_at=ts,
            ended_at=None,
            themes=list(themes or []),
        )

    def close(self, ended_at: Optional[datetime] = None) -> None:
        """Mark this chapter as closed."""
        self.ended_at = (ended_at or datetime.now(timezone.utc)).isoformat()

    @property
    def is_current(self) -> bool:
        return self.ended_at is None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "themes": self.themes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LifeArcChapter":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            started_at=data["started_at"],
            ended_at=data.get("ended_at"),
            themes=data.get("themes", []),
        )


@dataclass
class TurningPoint:
    """
    A significant inflection in the life arc, linking a narrative event to
    a chapter transition or major realisation.

    Attributes
    ----------
    id:
        Unique identifier.
    narrative_event_id:
        The narrative event at the centre of this turning point.
    description:
        Why this qualifies as a turning point.
    before_state:
        Description of the human's state before this point.
    after_state:
        Description of the human's state after this point.
    chapter_id:
        The life-arc chapter this turning point belongs to.
    """

    id: str
    narrative_event_id: str
    description: str
    before_state: str
    after_state: str
    chapter_id: str

    @classmethod
    def create(
        cls,
        narrative_event_id: str,
        description: str,
        before_state: str,
        after_state: str,
        chapter_id: str,
    ) -> "TurningPoint":
        return cls(
            id=str(uuid.uuid4()),
            narrative_event_id=narrative_event_id,
            description=description,
            before_state=before_state,
            after_state=after_state,
            chapter_id=chapter_id,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "narrative_event_id": self.narrative_event_id,
            "description": self.description,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "chapter_id": self.chapter_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TurningPoint":
        return cls(
            id=data["id"],
            narrative_event_id=data["narrative_event_id"],
            description=data["description"],
            before_state=data["before_state"],
            after_state=data["after_state"],
            chapter_id=data["chapter_id"],
        )


class NarrativeEngine:
    """
    Transforms raw episodes into a structured life-arc narrative.

    The engine maintains a registry of :class:`LifeArcChapter` objects and
    accumulates :class:`TurningPoint` records.  It writes derived
    :class:`~victor.memory.narrative.NarrativeEvent` objects into the
    provided :class:`~victor.memory.narrative.NarrativeMemory`.

    Parameters
    ----------
    narrative_memory:
        The narrative memory store to write enriched events into.
    """

    def __init__(self, narrative_memory: NarrativeMemory) -> None:
        self._narrative_memory = narrative_memory
        self._chapters: list[LifeArcChapter] = []
        self._turning_points: list[TurningPoint] = []

    # ------------------------------------------------------------------
    # Chapter management
    # ------------------------------------------------------------------

    def open_chapter(
        self,
        name: str,
        description: str,
        themes: Optional[list[str]] = None,
        started_at: Optional[datetime] = None,
    ) -> LifeArcChapter:
        """
        Open a new life-arc chapter.

        If there is a current open chapter it is *not* automatically closed;
        overlapping chapters are permitted to model multi-threaded life arcs.
        """
        chapter = LifeArcChapter.create(
            name=name,
            description=description,
            themes=themes,
            started_at=started_at,
        )
        self._chapters.append(chapter)
        return chapter

    def close_chapter(
        self, chapter_id: str, ended_at: Optional[datetime] = None
    ) -> None:
        """Mark the chapter with *chapter_id* as closed."""
        for chapter in self._chapters:
            if chapter.id == chapter_id:
                chapter.close(ended_at=ended_at)
                return
        raise KeyError(f"No chapter with id {chapter_id!r}")

    def current_chapter(self) -> Optional[LifeArcChapter]:
        """Return the most recently opened chapter that is still open."""
        open_chapters = [c for c in self._chapters if c.is_current]
        return open_chapters[-1] if open_chapters else None

    def all_chapters(self) -> list[LifeArcChapter]:
        return list(self._chapters)

    # ------------------------------------------------------------------
    # Narrative event processing
    # ------------------------------------------------------------------

    def process(
        self,
        episodes: list[Episode],
        meaning: str,
        chapter_id: Optional[str] = None,
        is_turning_point: bool = False,
        wound_or_breakthrough: Optional[str] = None,
        implications: Optional[list[str]] = None,
        pattern_tags: Optional[list[str]] = None,
        promises_or_vows: Optional[list[str]] = None,
        turning_point_description: Optional[str] = None,
        before_state: Optional[str] = None,
        after_state: Optional[str] = None,
    ) -> NarrativeEvent:
        """
        Create a :class:`NarrativeEvent` from one or more episodes and
        commit it to narrative memory.

        If *is_turning_point* is ``True`` a :class:`TurningPoint` record
        is also created and linked to the event.

        Parameters
        ----------
        episodes:
            One or more source episodes that inform this narrative event.
        meaning:
            Concise statement of why these episodes matter.
        chapter_id:
            Chapter this event belongs to.  Defaults to the current open
            chapter's ID if one exists.
        is_turning_point:
            Whether this event marks a significant inflection.
        wound_or_breakthrough:
            ``"wound"`` or ``"breakthrough"`` classification, or ``None``.
        implications:
            Forward-looking inferences from this event.
        pattern_tags:
            Recurring patterns this event exemplifies.
        promises_or_vows:
            Commitments made during or because of this event.
        turning_point_description:
            Required when *is_turning_point* is ``True``.
        before_state:
            Required when *is_turning_point* is ``True``.
        after_state:
            Required when *is_turning_point* is ``True``.
        """
        resolved_chapter = chapter_id
        if resolved_chapter is None:
            current = self.current_chapter()
            resolved_chapter = current.id if current else "uncategorised"

        event = NarrativeEvent.create(
            episode_ids=[e.id for e in episodes],
            meaning=meaning,
            life_arc_chapter=resolved_chapter,
            is_turning_point=is_turning_point,
            wound_or_breakthrough=wound_or_breakthrough,
            implications=implications,
            pattern_tags=pattern_tags,
            promises_or_vows=promises_or_vows,
        )
        self._narrative_memory.record(event)

        if is_turning_point:
            tp = TurningPoint.create(
                narrative_event_id=event.id,
                description=turning_point_description or meaning,
                before_state=before_state or "",
                after_state=after_state or "",
                chapter_id=resolved_chapter,
            )
            self._turning_points.append(tp)

        return event

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_turning_points(self) -> list[TurningPoint]:
        return list(self._turning_points)

    def detect_patterns(self) -> dict[str, int]:
        """
        Return a frequency map of all pattern tags across all narrative
        events stored in the underlying narrative memory.
        """
        counts: dict[str, int] = {}
        for event in self._narrative_memory.all():
            for tag in event.pattern_tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "chapters": [c.to_dict() for c in self._chapters],
            "turning_points": [tp.to_dict() for tp in self._turning_points],
        }

    @classmethod
    def from_dict(
        cls, data: dict, narrative_memory: NarrativeMemory
    ) -> "NarrativeEngine":
        engine = cls(narrative_memory)
        for raw in data.get("chapters", []):
            engine._chapters.append(LifeArcChapter.from_dict(raw))
        for raw in data.get("turning_points", []):
            engine._turning_points.append(TurningPoint.from_dict(raw))
        return engine
