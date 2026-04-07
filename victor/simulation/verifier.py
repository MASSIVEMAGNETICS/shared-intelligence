"""
SimulationVerifier — Branch simulation and plan verification loop.

Before major recommendations or actions, Victor runs branch simulations.
Each branch models a plausible future trajectory and is scored against
seven dimensions.  The verifier then evaluates whether a proposed plan
preserves mission continuity and advances the long arc.

This is where Victor stops being a smart chatbot and becomes a cognitive
operating system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SimulationBranch:
    """
    A single simulated future trajectory.

    All scores are normalised to ``[0.0, 1.0]`` unless noted.

    Attributes
    ----------
    id:
        Unique identifier.
    description:
        Human-readable description of this branch.
    predicted_gain:
        Estimated positive value delivered if this branch is taken.
    predicted_regret:
        Estimated regret if this branch is taken and fails.
    reversibility:
        How easily the human can course-correct after taking this branch
        (1.0 = fully reversible, 0.0 = irreversible).
    identity_drift_risk:
        Risk that this branch pulls the human away from their core
        identity and long-arc mission (0.0 = none, 1.0 = extreme).
    long_arc_alignment:
        How strongly this branch advances the human's long-arc mission
        (0.0 = unaligned, 1.0 = perfectly aligned).
    energy_cost:
        Estimated effort required (0.0 = trivial, 1.0 = exhausting).
    completion_probability:
        Estimated probability that the human will actually complete this
        branch if they choose it (0.0–1.0).
    metadata:
        Extensible key-value store.
    """

    id: str
    description: str
    predicted_gain: float
    predicted_regret: float
    reversibility: float
    identity_drift_risk: float
    long_arc_alignment: float
    energy_cost: float
    completion_probability: float
    metadata: dict

    @classmethod
    def create(
        cls,
        description: str,
        predicted_gain: float,
        predicted_regret: float,
        reversibility: float,
        identity_drift_risk: float,
        long_arc_alignment: float,
        energy_cost: float,
        completion_probability: float,
        metadata: Optional[dict] = None,
    ) -> "SimulationBranch":
        for name, value in [
            ("predicted_gain", predicted_gain),
            ("predicted_regret", predicted_regret),
            ("reversibility", reversibility),
            ("identity_drift_risk", identity_drift_risk),
            ("long_arc_alignment", long_arc_alignment),
            ("energy_cost", energy_cost),
            ("completion_probability", completion_probability),
        ]:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")
        return cls(
            id=str(uuid.uuid4()),
            description=description,
            predicted_gain=predicted_gain,
            predicted_regret=predicted_regret,
            reversibility=reversibility,
            identity_drift_risk=identity_drift_risk,
            long_arc_alignment=long_arc_alignment,
            energy_cost=energy_cost,
            completion_probability=completion_probability,
            metadata=dict(metadata or {}),
        )

    def composite_score(self) -> float:
        """
        Compute a single composite desirability score.

        Higher is better.  The formula weights gain, alignment, reversibility,
        and completion probability positively, and penalises regret, identity
        drift risk, and energy cost.

        Weight breakdown (positive → negative):
            predicted_gain        +0.25
            long_arc_alignment    +0.25
            reversibility         +0.15
            completion_probability+0.15
            predicted_regret      −0.10
            identity_drift_risk   −0.10
            energy_cost           −0.05
        """
        return (
            self.predicted_gain * 0.25
            + self.long_arc_alignment * 0.25
            + self.reversibility * 0.15
            + self.completion_probability * 0.15
            - self.predicted_regret * 0.10
            - self.identity_drift_risk * 0.10
            - self.energy_cost * 0.05
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "predicted_gain": self.predicted_gain,
            "predicted_regret": self.predicted_regret,
            "reversibility": self.reversibility,
            "identity_drift_risk": self.identity_drift_risk,
            "long_arc_alignment": self.long_arc_alignment,
            "energy_cost": self.energy_cost,
            "completion_probability": self.completion_probability,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationBranch":
        return cls(
            id=data["id"],
            description=data["description"],
            predicted_gain=data["predicted_gain"],
            predicted_regret=data["predicted_regret"],
            reversibility=data["reversibility"],
            identity_drift_risk=data["identity_drift_risk"],
            long_arc_alignment=data["long_arc_alignment"],
            energy_cost=data["energy_cost"],
            completion_probability=data["completion_probability"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class VerificationResult:
    """
    The output of a :class:`SimulationVerifier` run.

    Attributes
    ----------
    recommended_branch_id:
        ID of the branch the verifier recommends.
    mission_continuity_score:
        How well the recommended branch preserves mission continuity
        (0.0–1.0).
    identity_safe:
        ``True`` if the recommended branch's ``identity_drift_risk`` is
        below the safety threshold.
    reasoning:
        Human-readable explanation of the recommendation.
    ranked_branches:
        All branches ranked by composite score, highest first.
    """

    recommended_branch_id: Optional[str]
    mission_continuity_score: float
    identity_safe: bool
    reasoning: str
    ranked_branches: list[SimulationBranch]

    def to_dict(self) -> dict:
        return {
            "recommended_branch_id": self.recommended_branch_id,
            "mission_continuity_score": self.mission_continuity_score,
            "identity_safe": self.identity_safe,
            "reasoning": self.reasoning,
            "ranked_branches": [b.to_dict() for b in self.ranked_branches],
        }


class SimulationVerifier:
    """
    Evaluates a set of simulation branches and selects the one that best
    preserves mission continuity while minimising identity drift risk.

    Parameters
    ----------
    identity_drift_threshold:
        Branches whose ``identity_drift_risk`` exceeds this value are
        flagged as identity-unsafe (default ``0.4``).
    mission_continuity_weight:
        Weight given to ``long_arc_alignment`` when computing the mission
        continuity score (default ``1.0``).
    """

    def __init__(
        self,
        identity_drift_threshold: float = 0.4,
        mission_continuity_weight: float = 1.0,
    ) -> None:
        if not 0.0 <= identity_drift_threshold <= 1.0:
            raise ValueError("identity_drift_threshold must be in [0.0, 1.0]")
        self.identity_drift_threshold = identity_drift_threshold
        self.mission_continuity_weight = mission_continuity_weight

    def run(self, branches: list[SimulationBranch]) -> VerificationResult:
        """
        Evaluate *branches* and return a :class:`VerificationResult`.

        Parameters
        ----------
        branches:
            One or more candidate simulation branches.  Must be non-empty.
        """
        if not branches:
            return VerificationResult(
                recommended_branch_id=None,
                mission_continuity_score=0.0,
                identity_safe=False,
                reasoning="No branches provided for simulation.",
                ranked_branches=[],
            )

        ranked = sorted(branches, key=lambda b: b.composite_score(), reverse=True)
        best = ranked[0]
        identity_safe = best.identity_drift_risk <= self.identity_drift_threshold
        mission_score = best.long_arc_alignment * self.mission_continuity_weight

        parts: list[str] = [
            f"Branch '{best.description}' scored highest (composite "
            f"{best.composite_score():.3f}).",
            f"Long-arc alignment: {best.long_arc_alignment:.2f}.",
            f"Reversibility: {best.reversibility:.2f}.",
            f"Completion probability: {best.completion_probability:.2f}.",
        ]
        if not identity_safe:
            parts.append(
                f"WARNING: identity drift risk ({best.identity_drift_risk:.2f}) "
                f"exceeds threshold ({self.identity_drift_threshold:.2f}). "
                "Review before proceeding."
            )

        return VerificationResult(
            recommended_branch_id=best.id,
            mission_continuity_score=mission_score,
            identity_safe=identity_safe,
            reasoning=" ".join(parts),
            ranked_branches=ranked,
        )

    def reflect(
        self,
        intervention_summary: str,
        reduced_confusion: Optional[bool] = None,
        strengthened_discipline: Optional[bool] = None,
        preserved_intent: Optional[bool] = None,
        distorted_values: Optional[bool] = None,
        advanced_long_arc: Optional[bool] = None,
    ) -> dict:
        """
        Evaluate the effect a completed intervention had on the human.

        This is the self-correction loop: rather than asking "was the answer
        correct?", it asks whether the intervention moved the long arc
        forward and preserved identity integrity.

        The returned ``quality_score`` is in the range ``[-1.0, 1.0]``:

        * ``+1.0`` — all assessed dimensions had positive outcomes.
        * ``0.0``  — no dimensions assessed, or outcomes cancel out.
        * ``-1.0`` — all assessed dimensions had negative outcomes
          (e.g. values distorted, all other flags False).

        Negative scores are semantically meaningful: they indicate the
        intervention actively harmed alignment, discipline, or intent.

        Returns a structured reflection report dict.
        """
        # Positive indicators: presence of good outcomes
        positive_flags = [reduced_confusion, strengthened_discipline, preserved_intent, advanced_long_arc]
        assessed_positive_count = sum(1 for v in positive_flags if v is True)

        # distorted_values=False means no distortion occurred (positive)
        # distorted_values=True means distortion occurred (penalty)
        if distorted_values is False:
            assessed_positive_count += 1
        elif distorted_values is True:
            assessed_positive_count -= 1

        total_assessed = sum(
            1
            for v in [reduced_confusion, strengthened_discipline, preserved_intent, distorted_values, advanced_long_arc]
            if v is not None
        )
        quality_score = assessed_positive_count / total_assessed if total_assessed else 0.0

        return {
            "intervention_summary": intervention_summary,
            "reduced_confusion": reduced_confusion,
            "strengthened_discipline": strengthened_discipline,
            "preserved_intent": preserved_intent,
            "distorted_values": distorted_values,
            "advanced_long_arc": advanced_long_arc,
            "quality_score": quality_score,
            "assessed_at": datetime.now(timezone.utc).isoformat(),
        }
