"""Tests for SymbiosisModel."""

import pytest
from victor.symbiosis.model import (
    SymbiosisModel,
    InteractionRecord,
    InterventionType,
    InterventionOutcome,
)


def make_record(
    itype: InterventionType = InterventionType.ADVICE,
    outcome: InterventionOutcome = InterventionOutcome.ACTED_ON,
    emotional_state: str = "focused",
    tags: list | None = None,
) -> InteractionRecord:
    return InteractionRecord.create(
        intervention_type=itype,
        content_summary="Suggested prioritising sleep.",
        human_emotional_state=emotional_state,
        outcome=outcome,
        tags=tags or [],
    )


class TestInteractionRecord:
    def test_create(self):
        rec = make_record()
        assert rec.intervention_type == InterventionType.ADVICE
        assert rec.outcome == InterventionOutcome.ACTED_ON
        assert rec.id

    def test_round_trip(self):
        rec = make_record(itype=InterventionType.CHALLENGE, outcome=InterventionOutcome.BREAKTHROUGH)
        restored = InteractionRecord.from_dict(rec.to_dict())
        assert restored.id == rec.id
        assert restored.intervention_type == InterventionType.CHALLENGE
        assert restored.outcome == InterventionOutcome.BREAKTHROUGH


class TestSymbiosisModel:
    def _make_model(self) -> SymbiosisModel:
        model = SymbiosisModel()
        model.record(make_record(InterventionType.ADVICE, InterventionOutcome.BREAKTHROUGH, tags=["sleep"]))
        model.record(make_record(InterventionType.ADVICE, InterventionOutcome.IGNORED, tags=["productivity"]))
        model.record(make_record(InterventionType.CHALLENGE, InterventionOutcome.ACTED_ON, tags=["sleep"]))
        model.record(make_record(InterventionType.CHALLENGE, InterventionOutcome.BREAKTHROUGH))
        model.record(make_record(InterventionType.CHALLENGE, InterventionOutcome.BREAKTHROUGH))
        return model

    def test_len(self):
        model = self._make_model()
        assert len(model) == 5

    def test_effectiveness_by_type(self):
        model = self._make_model()
        eff = model.effectiveness_by_type()
        assert "advice" in eff
        assert "challenge" in eff
        assert eff["advice"]["breakthrough"] == 1
        assert eff["advice"]["ignored"] == 1

    def test_breakthrough_rate_all(self):
        model = self._make_model()
        rate = model.breakthrough_rate()
        assert rate == pytest.approx(3 / 5)

    def test_breakthrough_rate_by_type(self):
        model = self._make_model()
        challenge_rate = model.breakthrough_rate(InterventionType.CHALLENGE)
        # 2 breakthroughs out of 3 challenge records
        assert challenge_rate == pytest.approx(2 / 3)

    def test_ignored_rate(self):
        model = self._make_model()
        assert model.ignored_rate() == pytest.approx(1 / 5)

    def test_recurring_patterns(self):
        model = self._make_model()
        patterns = model.recurring_patterns(min_frequency=2)
        assert "sleep" in patterns
        assert "productivity" not in patterns  # only 1

    def test_emotional_state_correlations(self):
        model = self._make_model()
        corr = model.emotional_state_correlations()
        assert "focused" in corr

    def test_best_intervention_type(self):
        model = self._make_model()
        # challenge has higher breakthrough rate (2/3) than advice (1/2)
        best = model.best_intervention_type()
        assert best == InterventionType.CHALLENGE

    def test_best_intervention_none_when_insufficient_data(self):
        model = SymbiosisModel()
        # Fewer than 3 records per type → no qualifying type
        model.record(make_record(InterventionType.ADVICE, InterventionOutcome.BREAKTHROUGH))
        model.record(make_record(InterventionType.ADVICE, InterventionOutcome.IGNORED))
        assert model.best_intervention_type() is None

    def test_by_outcome(self):
        model = self._make_model()
        breakthroughs = model.by_outcome(InterventionOutcome.BREAKTHROUGH)
        assert len(breakthroughs) == 3

    def test_serialisation_round_trip(self):
        model = self._make_model()
        restored = SymbiosisModel.from_dict(model.to_dict())
        assert len(restored) == len(model)
        assert restored.breakthrough_rate() == pytest.approx(model.breakthrough_rate())
