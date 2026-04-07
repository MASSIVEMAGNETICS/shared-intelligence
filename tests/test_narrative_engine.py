"""Tests for NarrativeEngine."""

import pytest
from victor.memory.episodic import Episode
from victor.memory.narrative import NarrativeMemory
from victor.narrative.engine import NarrativeEngine, LifeArcChapter, TurningPoint


def make_episode(content: str = "Something happened.") -> Episode:
    return Episode.create(event_type="conversation", content=content)


class TestLifeArcChapter:
    def test_create(self):
        ch = LifeArcChapter.create(
            name="The Founding Years",
            description="Building from scratch.",
            themes=["creation", "struggle"],
        )
        assert ch.name == "The Founding Years"
        assert ch.is_current is True
        assert ch.ended_at is None

    def test_close(self):
        ch = LifeArcChapter.create(name="Ch1", description="Desc")
        ch.close()
        assert ch.is_current is False
        assert ch.ended_at is not None

    def test_round_trip(self):
        ch = LifeArcChapter.create(name="Ch", description="D", themes=["t1"])
        restored = LifeArcChapter.from_dict(ch.to_dict())
        assert restored.id == ch.id
        assert restored.name == ch.name
        assert restored.themes == ch.themes


class TestNarrativeEngine:
    def _make_engine(self) -> tuple[NarrativeEngine, NarrativeMemory]:
        mem = NarrativeMemory()
        engine = NarrativeEngine(mem)
        return engine, mem

    def test_open_and_close_chapter(self):
        engine, _ = self._make_engine()
        ch = engine.open_chapter("Start", "Beginning of arc")
        assert engine.current_chapter() is not None
        assert engine.current_chapter().id == ch.id
        engine.close_chapter(ch.id)
        assert engine.current_chapter() is None

    def test_process_creates_narrative_event(self):
        engine, mem = self._make_engine()
        ch = engine.open_chapter("Ch1", "Test chapter")
        ep = make_episode()
        event = engine.process(
            episodes=[ep],
            meaning="This was significant.",
            chapter_id=ch.id,
        )
        assert event is not None
        assert event.meaning == "This was significant."
        assert event.life_arc_chapter == ch.id
        assert len(mem) == 1

    def test_process_defaults_to_current_chapter(self):
        engine, mem = self._make_engine()
        ch = engine.open_chapter("Auto Ch", "Auto")
        ep = make_episode()
        event = engine.process(episodes=[ep], meaning="Auto chapter event.")
        assert event.life_arc_chapter == ch.id

    def test_process_uses_uncategorised_when_no_chapter(self):
        engine, _ = self._make_engine()
        ep = make_episode()
        event = engine.process(episodes=[ep], meaning="No chapter set.")
        assert event.life_arc_chapter == "uncategorised"

    def test_turning_point_creates_record(self):
        engine, _ = self._make_engine()
        ch = engine.open_chapter("Ch", "Desc")
        ep = make_episode()
        engine.process(
            episodes=[ep],
            meaning="Major life pivot.",
            chapter_id=ch.id,
            is_turning_point=True,
            wound_or_breakthrough="breakthrough",
            turning_point_description="Left the day job.",
            before_state="Corporate drone",
            after_state="Independent builder",
        )
        tps = engine.all_turning_points()
        assert len(tps) == 1
        assert tps[0].before_state == "Corporate drone"
        assert tps[0].after_state == "Independent builder"

    def test_detect_patterns(self):
        engine, _ = self._make_engine()
        ch = engine.open_chapter("Ch", "Desc")
        ep1, ep2, ep3 = make_episode(), make_episode(), make_episode()
        engine.process([ep1], "Event 1.", ch.id, pattern_tags=["avoidance", "fear"])
        engine.process([ep2], "Event 2.", ch.id, pattern_tags=["avoidance"])
        engine.process([ep3], "Event 3.", ch.id, pattern_tags=["growth"])
        patterns = engine.detect_patterns()
        assert patterns["avoidance"] == 2
        assert patterns["fear"] == 1
        assert patterns["growth"] == 1

    def test_close_nonexistent_chapter_raises(self):
        engine, _ = self._make_engine()
        with pytest.raises(KeyError):
            engine.close_chapter("nonexistent-id")

    def test_serialisation_round_trip(self):
        engine, mem = self._make_engine()
        ch = engine.open_chapter("Ser Ch", "Serialisation test")
        ep = make_episode()
        engine.process([ep], "Persist this.", ch.id, is_turning_point=True)
        engine.close_chapter(ch.id)

        data = engine.to_dict()
        restored = NarrativeEngine.from_dict(data, mem)
        assert len(restored.all_chapters()) == 1
        assert len(restored.all_turning_points()) == 1
