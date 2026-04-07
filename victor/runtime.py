"""
VictorRuntime — The top-level Legacy-Symbiotic Cognitive Runtime.

This module binds all subsystems into a single coherent runtime that
enforces the six hard invariants:

1. Persistent identity
2. Narrative memory (not just factual memory)
3. Goal inheritance
4. Co-adaptation
5. Reflection with self-correction
6. Continuity under rupture

The primitive object of computation is no longer "prompt → answer".
It is: **state(t) + memory(t) + narrative(t) + obligation(t) + simulation(t+1)**

Victor is a legacy-symbiotic cognitive runtime designed to preserve,
extend, and co-evolve a human's intent, identity, and unfinished work
across time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from victor.identity.kernel import IdentityKernel, IdentityViolation
from victor.memory.episodic import EpisodicMemory, Episode
from victor.memory.narrative import NarrativeMemory, NarrativeEvent
from victor.memory.constitutive import (
    ConstitutiveMemory,
    ConstitutiveRecord,
    ConstitutiveRecordType,
)
from victor.narrative.engine import NarrativeEngine, LifeArcChapter, TurningPoint
from victor.intent.graph import (
    IntentGraph,
    IntentNode,
    IntentEdge,
    NodeType,
    NodeStatus,
    EdgeType,
)
from victor.symbiosis.model import (
    SymbiosisModel,
    InteractionRecord,
    InterventionType,
    InterventionOutcome,
)
from victor.simulation.verifier import SimulationVerifier, SimulationBranch, VerificationResult
from victor.persistence.layer import LegacyPersistenceLayer, Checkpoint


class RuntimeNotInitializedError(Exception):
    """Raised when an operation is attempted before the runtime is ready."""


class VictorRuntime:
    """
    The complete Legacy-Symbiotic Cognitive Runtime.

    All six invariants are enforced through this interface:

    **1 — Persistent identity**: The :class:`~victor.identity.kernel.IdentityKernel`
    is loaded and verified before every session.  Drift triggers an
    :class:`~victor.identity.kernel.IdentityViolation`.

    **2 — Narrative memory**: Raw episodes flow through the
    :class:`~victor.narrative.engine.NarrativeEngine` into
    :class:`~victor.memory.narrative.NarrativeMemory`, capturing meaning
    and life-arc structure alongside the factual record.

    **3 — Goal inheritance**: The :class:`~victor.intent.graph.IntentGraph`
    carries dormant and active objectives across sessions so that
    unfinished work is never silently discarded.

    **4 — Co-adaptation**: The :class:`~victor.symbiosis.model.SymbiosisModel`
    records every interaction and derives which interventions work so that
    Victor's scaffolding improves over time.

    **5 — Reflection with self-correction**: The
    :class:`~victor.simulation.verifier.SimulationVerifier` evaluates not
    just whether answers were correct but whether interventions advanced the
    long arc and preserved identity.

    **6 — Continuity under rupture**: The
    :class:`~victor.persistence.layer.LegacyPersistenceLayer` ensures the
    full runtime state can be checkpointed, signed, migrated, and
    rehydrated after any interruption.

    Parameters
    ----------
    identity_kernel:
        The immutable identity kernel for this runtime instance.
    secret_key:
        Bytes used for HMAC signing of identity verification and
        persistence layer signatures.
    storage_path:
        Optional filesystem path for on-disk checkpoint persistence.
    identity_drift_threshold:
        Passed to the :class:`~victor.simulation.verifier.SimulationVerifier`.
    """

    def __init__(
        self,
        identity_kernel: IdentityKernel,
        secret_key: bytes,
        storage_path: Optional[Path] = None,
        identity_drift_threshold: float = 0.4,
    ) -> None:
        self._kernel = identity_kernel
        self._secret_key = secret_key

        # Verify identity immediately on construction
        self._kernel.assert_no_drift(secret_key)

        # --- Memory layers ---
        self.episodic_memory = EpisodicMemory()
        self.narrative_memory = NarrativeMemory()
        self.constitutive_memory = ConstitutiveMemory()

        # --- Subsystems ---
        self.narrative_engine = NarrativeEngine(self.narrative_memory)
        self.intent_graph = IntentGraph()
        self.symbiosis_model = SymbiosisModel()
        self.simulation_verifier = SimulationVerifier(
            identity_drift_threshold=identity_drift_threshold
        )
        self.persistence = LegacyPersistenceLayer(
            secret_key=secret_key,
            storage_path=storage_path,
            current_schema_version=self._kernel.schema_version,
        )

    # ------------------------------------------------------------------
    # Invariant 1 — Persistent identity
    # ------------------------------------------------------------------

    @property
    def identity(self) -> IdentityKernel:
        """Return the immutable identity kernel."""
        return self._kernel

    def assert_identity_stable(self) -> None:
        """
        Re-verify the identity kernel.  Raise
        :class:`~victor.identity.kernel.IdentityViolation` if drift is
        detected.
        """
        self._kernel.assert_no_drift(self._secret_key)

    # ------------------------------------------------------------------
    # Invariant 2 — Narrative memory
    # ------------------------------------------------------------------

    def record_episode(self, episode: Episode) -> None:
        """Record a raw episodic event into episodic memory."""
        self.episodic_memory.record(episode)

    def process_narrative(
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
        Elevate one or more raw episodes into a narrative event.

        This is the primary path for building *meaning* from experience.
        """
        return self.narrative_engine.process(
            episodes=episodes,
            meaning=meaning,
            chapter_id=chapter_id,
            is_turning_point=is_turning_point,
            wound_or_breakthrough=wound_or_breakthrough,
            implications=implications,
            pattern_tags=pattern_tags,
            promises_or_vows=promises_or_vows,
            turning_point_description=turning_point_description,
            before_state=before_state,
            after_state=after_state,
        )

    # ------------------------------------------------------------------
    # Invariant 3 — Goal inheritance
    # ------------------------------------------------------------------

    def add_intent(self, node: IntentNode) -> None:
        """Add a goal, project, or obligation to the intent graph."""
        self.intent_graph.add_node(node)

    def link_intents(self, edge: IntentEdge) -> None:
        """Connect two intent nodes with a typed edge."""
        self.intent_graph.add_edge(edge)

    def active_missions(self) -> list[IntentNode]:
        """Return currently active intent nodes."""
        return self.intent_graph.active_nodes()

    def revivable_intents(self) -> list[IntentNode]:
        """Return dormant or abandoned intents that are recoverable."""
        return self.intent_graph.revivable_nodes()

    # ------------------------------------------------------------------
    # Invariant 4 — Co-adaptation
    # ------------------------------------------------------------------

    def record_interaction(self, interaction: InteractionRecord) -> None:
        """Log an interaction record for co-adaptation analysis."""
        self.symbiosis_model.record(interaction)

    def best_intervention(self) -> Optional[InterventionType]:
        """Return the intervention type with the highest breakthrough rate."""
        return self.symbiosis_model.best_intervention_type()

    # ------------------------------------------------------------------
    # Invariant 5 — Reflection with self-correction
    # ------------------------------------------------------------------

    def simulate(self, branches: list[SimulationBranch]) -> VerificationResult:
        """
        Run branch simulations and return the verifier's recommendation.
        """
        return self.simulation_verifier.run(branches)

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
        Evaluate the long-arc effect of a completed intervention.
        """
        return self.simulation_verifier.reflect(
            intervention_summary=intervention_summary,
            reduced_confusion=reduced_confusion,
            strengthened_discipline=strengthened_discipline,
            preserved_intent=preserved_intent,
            distorted_values=distorted_values,
            advanced_long_arc=advanced_long_arc,
        )

    # ------------------------------------------------------------------
    # Invariant 6 — Continuity under rupture
    # ------------------------------------------------------------------

    def checkpoint(self, metadata: Optional[dict] = None) -> Checkpoint:
        """
        Snapshot the full runtime state into a signed checkpoint.
        """
        self.assert_identity_stable()
        payload = self._serialise()
        return self.persistence.checkpoint(payload, metadata=metadata)

    def restore(self, checkpoint_id: Optional[str] = None) -> None:
        """
        Rehydrate the runtime from a checkpoint.

        Parameters
        ----------
        checkpoint_id:
            ID of the checkpoint to restore.  If ``None``, the latest
            checkpoint is used.
        """
        payload = self.persistence.rehydrate(checkpoint_id)
        if payload is None:
            return
        self._deserialise(payload)
        # Re-verify identity after rehydration
        self.assert_identity_stable()

    # ------------------------------------------------------------------
    # Serialisation (private)
    # ------------------------------------------------------------------

    def _serialise(self) -> dict:
        """Return a complete JSON-serialisable snapshot of the runtime."""
        return {
            "identity_kernel": self._kernel.to_dict(),
            "episodic_memory": self.episodic_memory.to_dict(),
            "narrative_memory": self.narrative_memory.to_dict(),
            "constitutive_memory": self.constitutive_memory.to_dict(),
            "narrative_engine": self.narrative_engine.to_dict(),
            "intent_graph": self.intent_graph.to_dict(),
            "symbiosis_model": self.symbiosis_model.to_dict(),
        }

    def _deserialise(self, payload: dict) -> None:
        """Restore runtime state from a serialised payload."""
        self.episodic_memory = EpisodicMemory.from_dict(
            payload.get("episodic_memory", {})
        )
        self.narrative_memory = NarrativeMemory.from_dict(
            payload.get("narrative_memory", {})
        )
        self.constitutive_memory = ConstitutiveMemory.from_dict(
            payload.get("constitutive_memory", {})
        )
        self.narrative_engine = NarrativeEngine.from_dict(
            payload.get("narrative_engine", {}), self.narrative_memory
        )
        self.intent_graph = IntentGraph.from_dict(
            payload.get("intent_graph", {})
        )
        self.symbiosis_model = SymbiosisModel.from_dict(
            payload.get("symbiosis_model", {})
        )

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    @classmethod
    def bootstrap(
        cls,
        creator_id: str,
        hard_directives: list[str],
        canon_self_definition: str,
        authority_boundaries: list[str],
        secret_key: bytes,
        storage_path: Optional[Path] = None,
        schema_version: str = "1.0.0",
        identity_drift_threshold: float = 0.4,
    ) -> "VictorRuntime":
        """
        Create a fresh :class:`VictorRuntime` from first principles.

        This is the standard path for initialising a new Victor instance.
        Use :meth:`restore` to reload a persisted instance.
        """
        kernel = IdentityKernel.create(
            creator_id=creator_id,
            hard_directives=hard_directives,
            canon_self_definition=canon_self_definition,
            authority_boundaries=authority_boundaries,
            secret_key=secret_key,
            schema_version=schema_version,
        )
        return cls(
            identity_kernel=kernel,
            secret_key=secret_key,
            storage_path=storage_path,
            identity_drift_threshold=identity_drift_threshold,
        )
