"""
SymbiosisModel — Tracks the co-adaptive interaction between Victor and its creator.

The symbiosis model is the co-evolution layer.  It records interactions,
measures which interventions produce breakthroughs vs. which get ignored,
and tracks recurring behavioural patterns so that Victor can tailor its
cognitive scaffolding to maximise long-term impact on the human's trajectory.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class InterventionType(str, Enum):
    """How Victor intervened in the interaction."""

    ADVICE = "advice"
    CHALLENGE = "challenge"
    REFRAME = "reframe"
    PLANNING = "planning"
    REFLECTION = "reflection"
    EMOTIONAL_SUPPORT = "emotional_support"
    ACCOUNTABILITY = "accountability"
    INFORMATION = "information"


class InterventionOutcome(str, Enum):
    """What effect the intervention had on the human's behaviour."""

    BREAKTHROUGH = "breakthrough"
    ACTED_ON = "acted_on"
    PARTIALLY_ACTED_ON = "partially_acted_on"
    IGNORED = "ignored"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass
class InteractionRecord:
    """
    A single interaction between Victor and the human.

    Attributes
    ----------
    id:
        Unique identifier.
    timestamp:
        ISO-8601 UTC when the interaction occurred.
    intervention_type:
        What type of cognitive scaffolding Victor deployed.
    content_summary:
        Brief description of what was said or suggested.
    human_emotional_state:
        Estimated emotional state of the human at the time
        (free-text label, e.g. ``"anxious"``, ``"focused"``).
    outcome:
        Observed outcome of the intervention.
    follow_up_behaviour:
        What the human did following the interaction (may be empty).
    tags:
        Arbitrary labels for retrieval and analysis.
    metadata:
        Extensible key-value store.
    """

    id: str
    timestamp: str  # ISO-8601 UTC
    intervention_type: InterventionType
    content_summary: str
    human_emotional_state: str
    outcome: InterventionOutcome
    follow_up_behaviour: str
    tags: list[str]
    metadata: dict

    @classmethod
    def create(
        cls,
        intervention_type: InterventionType,
        content_summary: str,
        human_emotional_state: str = "",
        outcome: InterventionOutcome = InterventionOutcome.UNKNOWN,
        follow_up_behaviour: str = "",
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> "InteractionRecord":
        return cls(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            intervention_type=intervention_type,
            content_summary=content_summary,
            human_emotional_state=human_emotional_state,
            outcome=outcome,
            follow_up_behaviour=follow_up_behaviour,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "intervention_type": self.intervention_type.value,
            "content_summary": self.content_summary,
            "human_emotional_state": self.human_emotional_state,
            "outcome": self.outcome.value,
            "follow_up_behaviour": self.follow_up_behaviour,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionRecord":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            intervention_type=InterventionType(data["intervention_type"]),
            content_summary=data["content_summary"],
            human_emotional_state=data.get("human_emotional_state", ""),
            outcome=InterventionOutcome(data.get("outcome", "unknown")),
            follow_up_behaviour=data.get("follow_up_behaviour", ""),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class SymbiosisModel:
    """
    Co-adaptive interaction tracker between Victor and its creator.

    The model aggregates :class:`InteractionRecord` entries and derives
    statistics about which intervention types work, which patterns recur,
    and what emotional states correlate with productive outcomes.
    """

    def __init__(self) -> None:
        self._records: list[InteractionRecord] = []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, interaction: InteractionRecord) -> None:
        """Append an interaction record."""
        self._records.append(interaction)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def effectiveness_by_type(self) -> dict[str, dict[str, int]]:
        """
        Return a breakdown of outcome counts per intervention type.

        Returns
        -------
        dict
            ``{intervention_type: {outcome: count, …}, …}``
        """
        result: dict[str, dict[str, int]] = {}
        for rec in self._records:
            itype = rec.intervention_type.value
            outcome = rec.outcome.value
            result.setdefault(itype, {})
            result[itype][outcome] = result[itype].get(outcome, 0) + 1
        return result

    def breakthrough_rate(self, intervention_type: Optional[InterventionType] = None) -> float:
        """
        Fraction of interactions that resulted in a breakthrough.

        Parameters
        ----------
        intervention_type:
            If provided, restrict analysis to this type.
        """
        subset = self._records
        if intervention_type is not None:
            subset = [r for r in subset if r.intervention_type == intervention_type]
        if not subset:
            return 0.0
        breakthroughs = sum(
            1 for r in subset if r.outcome == InterventionOutcome.BREAKTHROUGH
        )
        return breakthroughs / len(subset)

    def ignored_rate(self, intervention_type: Optional[InterventionType] = None) -> float:
        """Fraction of interactions that were ignored."""
        subset = self._records
        if intervention_type is not None:
            subset = [r for r in subset if r.intervention_type == intervention_type]
        if not subset:
            return 0.0
        ignored = sum(1 for r in subset if r.outcome == InterventionOutcome.IGNORED)
        return ignored / len(subset)

    def recurring_patterns(self, min_frequency: int = 2) -> list[str]:
        """
        Return tags that appear in at least *min_frequency* records.
        """
        counts: dict[str, int] = {}
        for rec in self._records:
            for tag in rec.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return [tag for tag, count in counts.items() if count >= min_frequency]

    def emotional_state_correlations(self) -> dict[str, dict[str, int]]:
        """
        Return outcome distribution grouped by human emotional state at
        the time of the interaction.

        Returns
        -------
        dict
            ``{emotional_state: {outcome: count, …}, …}``
        """
        result: dict[str, dict[str, int]] = {}
        for rec in self._records:
            state = rec.human_emotional_state or "unknown"
            outcome = rec.outcome.value
            result.setdefault(state, {})
            result[state][outcome] = result[state].get(outcome, 0) + 1
        return result

    def best_intervention_type(self) -> Optional[InterventionType]:
        """
        Return the intervention type with the highest breakthrough rate
        (minimum 3 samples required to qualify).
        """
        rates: dict[InterventionType, float] = {}
        for itype in InterventionType:
            subset = [r for r in self._records if r.intervention_type == itype]
            if len(subset) >= 3:
                rates[itype] = sum(
                    1 for r in subset if r.outcome == InterventionOutcome.BREAKTHROUGH
                ) / len(subset)
        if not rates:
            return None
        return max(rates, key=lambda k: rates[k])

    def all_records(self) -> list[InteractionRecord]:
        return list(self._records)

    def by_outcome(self, outcome: InterventionOutcome) -> list[InteractionRecord]:
        return [r for r in self._records if r.outcome == outcome]

    def __len__(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"records": [r.to_dict() for r in self._records]}

    @classmethod
    def from_dict(cls, data: dict) -> "SymbiosisModel":
        model = cls()
        for raw in data.get("records", []):
            model.record(InteractionRecord.from_dict(raw))
        return model
