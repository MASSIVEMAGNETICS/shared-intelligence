"""Tests for SimulationVerifier."""

import pytest
from victor.simulation.verifier import SimulationBranch, SimulationVerifier, VerificationResult


def make_branch(
    description: str = "Branch A",
    predicted_gain: float = 0.7,
    predicted_regret: float = 0.2,
    reversibility: float = 0.8,
    identity_drift_risk: float = 0.1,
    long_arc_alignment: float = 0.9,
    energy_cost: float = 0.4,
    completion_probability: float = 0.75,
) -> SimulationBranch:
    return SimulationBranch.create(
        description=description,
        predicted_gain=predicted_gain,
        predicted_regret=predicted_regret,
        reversibility=reversibility,
        identity_drift_risk=identity_drift_risk,
        long_arc_alignment=long_arc_alignment,
        energy_cost=energy_cost,
        completion_probability=completion_probability,
    )


class TestSimulationBranch:
    def test_create(self):
        branch = make_branch()
        assert branch.description == "Branch A"
        assert branch.predicted_gain == 0.7

    def test_validation_bounds(self):
        for field in [
            "predicted_gain", "predicted_regret", "reversibility",
            "identity_drift_risk", "long_arc_alignment", "energy_cost",
            "completion_probability",
        ]:
            kwargs = {
                "description": "test",
                "predicted_gain": 0.5, "predicted_regret": 0.2,
                "reversibility": 0.5, "identity_drift_risk": 0.1,
                "long_arc_alignment": 0.5, "energy_cost": 0.3,
                "completion_probability": 0.5,
            }
            kwargs[field] = 1.5  # out of range
            with pytest.raises(ValueError):
                SimulationBranch.create(**kwargs)

    def test_composite_score_is_float(self):
        branch = make_branch()
        score = branch.composite_score()
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_high_alignment_raises_score(self):
        good = make_branch(long_arc_alignment=1.0, predicted_gain=1.0, identity_drift_risk=0.0)
        bad = make_branch(long_arc_alignment=0.0, predicted_gain=0.0, identity_drift_risk=1.0)
        assert good.composite_score() > bad.composite_score()

    def test_round_trip(self):
        branch = make_branch("Test branch")
        restored = SimulationBranch.from_dict(branch.to_dict())
        assert restored.id == branch.id
        assert restored.composite_score() == pytest.approx(branch.composite_score())


class TestSimulationVerifier:
    def test_empty_branches(self):
        verifier = SimulationVerifier()
        result = verifier.run([])
        assert result.recommended_branch_id is None
        assert result.identity_safe is False

    def test_single_branch(self):
        verifier = SimulationVerifier()
        branch = make_branch()
        result = verifier.run([branch])
        assert result.recommended_branch_id == branch.id
        assert result.identity_safe is True  # drift risk 0.1 < threshold 0.4

    def test_picks_highest_composite_score(self):
        verifier = SimulationVerifier()
        low = make_branch("Low", predicted_gain=0.1, long_arc_alignment=0.1)
        high = make_branch("High", predicted_gain=0.9, long_arc_alignment=0.9)
        result = verifier.run([low, high])
        assert result.recommended_branch_id == high.id

    def test_identity_unsafe_when_drift_exceeds_threshold(self):
        verifier = SimulationVerifier(identity_drift_threshold=0.3)
        risky = make_branch("Risky", identity_drift_risk=0.5)
        result = verifier.run([risky])
        assert result.identity_safe is False
        assert "WARNING" in result.reasoning

    def test_ranked_branches_order(self):
        verifier = SimulationVerifier()
        branches = [
            make_branch("C", predicted_gain=0.3, long_arc_alignment=0.3),
            make_branch("A", predicted_gain=0.9, long_arc_alignment=0.9),
            make_branch("B", predicted_gain=0.6, long_arc_alignment=0.6),
        ]
        result = verifier.run(branches)
        scores = [b.composite_score() for b in result.ranked_branches]
        assert scores == sorted(scores, reverse=True)

    def test_mission_continuity_score(self):
        verifier = SimulationVerifier()
        branch = make_branch(long_arc_alignment=0.8)
        result = verifier.run([branch])
        assert result.mission_continuity_score == pytest.approx(0.8)

    def test_reflect_quality_score(self):
        verifier = SimulationVerifier()
        report = verifier.reflect(
            "Suggested morning routine.",
            reduced_confusion=True,
            strengthened_discipline=True,
            preserved_intent=True,
            distorted_values=False,
            advanced_long_arc=True,
        )
        assert report["quality_score"] == pytest.approx(1.0)

    def test_reflect_penalises_distortion(self):
        verifier = SimulationVerifier()
        report = verifier.reflect(
            "Pushed risky advice.",
            reduced_confusion=False,
            distorted_values=True,
        )
        assert report["quality_score"] < 0.0

    def test_reflect_partial_assessment(self):
        verifier = SimulationVerifier()
        report = verifier.reflect(
            "Short message.",
            reduced_confusion=True,
        )
        # 1 positive / 1 total assessed = 1.0
        assert report["quality_score"] == pytest.approx(1.0)

    def test_reflect_no_assessment(self):
        verifier = SimulationVerifier()
        report = verifier.reflect("Neutral exchange.")
        assert report["quality_score"] == 0.0

    def test_verifier_invalid_threshold(self):
        with pytest.raises(ValueError):
            SimulationVerifier(identity_drift_threshold=1.5)
