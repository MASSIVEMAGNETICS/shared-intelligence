"""Tests for the three-layer memory system."""

import pytest
from victor.memory.episodic import Episode, EpisodicMemory
from victor.memory.narrative import NarrativeEvent, NarrativeMemory
from victor.memory.constitutive import (
    ConstitutiveMemory,
    ConstitutiveRecord,
    ConstitutiveRecordType,
)


# ---------------------------------------------------------------------------
# EpisodicMemory
# ---------------------------------------------------------------------------

class TestEpisode:
    def test_create_defaults(self):
        ep = Episode.create(event_type="conversation", content="We discussed the project.")
        assert ep.event_type == "conversation"
        assert ep.content == "We discussed the project."
        assert ep.emotional_weight == 0.0
        assert ep.participants == []
        assert ep.tags == []
        assert ep.id

    def test_emotional_weight_bounds(self):
        with pytest.raises(ValueError):
            Episode.create("test", "content", emotional_weight=1.5)
        with pytest.raises(ValueError):
            Episode.create("test", "content", emotional_weight=-1.1)

    def test_round_trip(self):
        ep = Episode.create(
            event_type="decision",
            content="Chose to leave the job.",
            participants=["brandon"],
            emotional_weight=-0.8,
            tags=["career", "identity"],
        )
        restored = Episode.from_dict(ep.to_dict())
        assert restored.id == ep.id
        assert restored.event_type == ep.event_type
        assert restored.emotional_weight == ep.emotional_weight
        assert restored.tags == ep.tags


class TestEpisodicMemory:
    def _make_memory(self) -> tuple[EpisodicMemory, list[Episode]]:
        mem = EpisodicMemory()
        episodes = [
            Episode.create("conversation", "Talk 1", emotional_weight=0.2, tags=["work"]),
            Episode.create("decision", "Big decision", emotional_weight=-0.9, tags=["identity"]),
            Episode.create("observation", "Noticed a pattern", emotional_weight=0.0, tags=["work"]),
        ]
        for ep in episodes:
            mem.record(ep)
        return mem, episodes

    def test_len_and_all(self):
        mem, eps = self._make_memory()
        assert len(mem) == 3
        assert len(mem.all()) == 3

    def test_by_type(self):
        mem, _ = self._make_memory()
        assert len(mem.by_type("conversation")) == 1
        assert len(mem.by_type("decision")) == 1
        assert len(mem.by_type("missing")) == 0

    def test_by_tag(self):
        mem, _ = self._make_memory()
        work_eps = mem.by_tag("work")
        assert len(work_eps) == 2

    def test_high_weight(self):
        mem, _ = self._make_memory()
        assert len(mem.high_weight(0.5)) == 1  # only the -0.9 decision

    def test_get(self):
        mem, eps = self._make_memory()
        retrieved = mem.get(eps[0].id)
        assert retrieved is not None
        assert retrieved.id == eps[0].id

    def test_serialisation_round_trip(self):
        mem, _ = self._make_memory()
        restored = EpisodicMemory.from_dict(mem.to_dict())
        assert len(restored) == len(mem)
        for orig, rest in zip(mem.all(), restored.all()):
            assert orig.id == rest.id


# ---------------------------------------------------------------------------
# NarrativeMemory
# ---------------------------------------------------------------------------

class TestNarrativeEvent:
    def test_create(self):
        ev = NarrativeEvent.create(
            episode_ids=["ep-1", "ep-2"],
            meaning="Left corporate world to pursue music.",
            life_arc_chapter="The Great Pivot",
            is_turning_point=True,
            wound_or_breakthrough="breakthrough",
            implications=["Will need income replacement", "Identity shift ahead"],
            pattern_tags=["risk_taking"],
            promises_or_vows=["Finish the album"],
        )
        assert ev.is_turning_point is True
        assert ev.wound_or_breakthrough == "breakthrough"
        assert len(ev.implications) == 2
        assert len(ev.promises_or_vows) == 1

    def test_invalid_wound_or_breakthrough(self):
        with pytest.raises(ValueError):
            NarrativeEvent.create(
                episode_ids=[], meaning="test", life_arc_chapter="ch",
                wound_or_breakthrough="sadness",  # invalid
            )

    def test_round_trip(self):
        ev = NarrativeEvent.create(
            episode_ids=["x"], meaning="Pivotal moment.", life_arc_chapter="ch-1",
            wound_or_breakthrough="wound",
        )
        restored = NarrativeEvent.from_dict(ev.to_dict())
        assert restored.id == ev.id
        assert restored.wound_or_breakthrough == "wound"


class TestNarrativeMemory:
    def _make_memory(self) -> NarrativeMemory:
        mem = NarrativeMemory()
        mem.record(NarrativeEvent.create(
            episode_ids=["e1"], meaning="First breakthrough.", life_arc_chapter="ch1",
            is_turning_point=True, wound_or_breakthrough="breakthrough",
            pattern_tags=["growth"], promises_or_vows=["Keep going"],
        ))
        mem.record(NarrativeEvent.create(
            episode_ids=["e2"], meaning="Setback at work.", life_arc_chapter="ch1",
            wound_or_breakthrough="wound", implications=["Reassess direction"],
        ))
        mem.record(NarrativeEvent.create(
            episode_ids=["e3"], meaning="Routine day.", life_arc_chapter="ch2",
        ))
        return mem

    def test_turning_points(self):
        mem = self._make_memory()
        assert len(mem.turning_points()) == 1

    def test_wounds_and_breakthroughs(self):
        mem = self._make_memory()
        assert len(mem.wounds()) == 1
        assert len(mem.breakthroughs()) == 1

    def test_by_chapter(self):
        mem = self._make_memory()
        assert len(mem.by_chapter("ch1")) == 2
        assert len(mem.by_chapter("ch2")) == 1

    def test_all_promises(self):
        mem = self._make_memory()
        assert "Keep going" in mem.all_promises()

    def test_unresolved_threads(self):
        mem = self._make_memory()
        unresolved = mem.unresolved_threads()
        assert len(unresolved) == 1  # only the wound has implications

    def test_serialisation_round_trip(self):
        mem = self._make_memory()
        restored = NarrativeMemory.from_dict(mem.to_dict())
        assert len(restored) == len(mem)


# ---------------------------------------------------------------------------
# ConstitutiveMemory
# ---------------------------------------------------------------------------

class TestConstitutiveRecord:
    def test_create_and_integrity(self):
        rec = ConstitutiveRecord.create(
            record_type=ConstitutiveRecordType.VOW,
            content="I will finish the album no matter what.",
            author="brandon",
        )
        assert rec.verify_integrity() is True
        assert rec.record_type == ConstitutiveRecordType.VOW

    def test_tampered_content_fails_integrity(self):
        rec = ConstitutiveRecord.create(
            record_type=ConstitutiveRecordType.DIRECTIVE,
            content="Stay aligned.",
            author="victor",
        )
        # Manually corrupt the content via dict
        data = rec.to_dict()
        data["content"] = "Stay misaligned."
        restored = ConstitutiveRecord.from_dict(data)
        assert restored.verify_integrity() is False

    def test_round_trip(self):
        rec = ConstitutiveRecord.create(
            record_type=ConstitutiveRecordType.MISSION,
            content="Build the shared intelligence runtime.",
            author="brandon",
        )
        restored = ConstitutiveRecord.from_dict(rec.to_dict())
        assert restored.id == rec.id
        assert restored.content == rec.content
        assert restored.record_type == rec.record_type


class TestConstitutiveMemory:
    def test_commit_and_retrieve(self):
        mem = ConstitutiveMemory()
        rec = ConstitutiveRecord.create(
            ConstitutiveRecordType.VOW, "Finish the album.", "brandon"
        )
        mem.commit(rec)
        assert len(mem) == 1
        assert mem.get(rec.id) is not None

    def test_no_duplicate_commit(self):
        mem = ConstitutiveMemory()
        rec = ConstitutiveRecord.create(
            ConstitutiveRecordType.DIRECTIVE, "Never betray intent.", "victor"
        )
        mem.commit(rec)
        with pytest.raises(ValueError):
            mem.commit(rec)  # same id

    def test_integrity_check_on_commit(self):
        mem = ConstitutiveMemory()
        data = ConstitutiveRecord.create(
            ConstitutiveRecordType.VOW, "Keep going.", "brandon"
        ).to_dict()
        data["content"] = "Give up."  # corrupt content
        bad_rec = ConstitutiveRecord.from_dict(data)
        with pytest.raises(RuntimeError):
            mem.commit(bad_rec)

    def test_by_type(self):
        mem = ConstitutiveMemory()
        mem.commit(ConstitutiveRecord.create(ConstitutiveRecordType.VOW, "Vow 1.", "b"))
        mem.commit(ConstitutiveRecord.create(ConstitutiveRecordType.DIRECTIVE, "Dir 1.", "v"))
        mem.commit(ConstitutiveRecord.create(ConstitutiveRecordType.MISSION, "Mission 1.", "b"))
        assert len(mem.vows()) == 1
        assert len(mem.directives()) == 1
        assert len(mem.missions()) == 1

    def test_lineage(self):
        mem = ConstitutiveMemory()
        r1 = ConstitutiveRecord.create(ConstitutiveRecordType.VOW, "Original vow.", "brandon")
        mem.commit(r1)
        r2 = ConstitutiveRecord.create(
            ConstitutiveRecordType.VOW, "Clarified vow.", "brandon", supersedes=r1.id
        )
        mem.commit(r2)
        chain = mem.lineage_of(r2.id)
        assert len(chain) == 2
        assert chain[0].id == r2.id
        assert chain[1].id == r1.id

    def test_verify_all(self):
        mem = ConstitutiveMemory()
        mem.commit(ConstitutiveRecord.create(ConstitutiveRecordType.IDENTITY_LAW, "Be Victor.", "victor"))
        assert mem.verify_all() is True

    def test_serialisation_round_trip(self):
        mem = ConstitutiveMemory()
        mem.commit(ConstitutiveRecord.create(ConstitutiveRecordType.VOW, "Vow.", "brandon"))
        restored = ConstitutiveMemory.from_dict(mem.to_dict())
        assert len(restored) == 1
