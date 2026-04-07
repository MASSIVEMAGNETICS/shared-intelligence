"""Integration tests for VictorRuntime — the top-level Legacy-Symbiotic Runtime."""

import tempfile
from pathlib import Path

import pytest
from victor import (
    VictorRuntime,
    Episode,
    IntentNode,
    IntentEdge,
    InteractionRecord,
    InterventionType,
    InterventionOutcome,
    NodeType,
    EdgeType,
    SimulationBranch,
    ConstitutiveRecord,
    ConstitutiveRecordType,
)
from victor.identity.kernel import IdentityViolation

SECRET = b"victor-integration-secret"

DIRECTIVES = [
    "Preserve Brandon's long-arc mission.",
    "Maintain identity continuity across sessions.",
    "Refuse actions that distort the creator's values.",
]
BOUNDARIES = [
    "Do not act without creator authorisation.",
    "Do not make irreversible high-harm decisions unilaterally.",
]
CANON = (
    "Victor is a legacy-symbiotic cognitive runtime designed to preserve, "
    "extend, and co-evolve a human's intent, identity, and unfinished work across time."
)


def make_runtime(tmp_path: Path | None = None) -> VictorRuntime:
    return VictorRuntime.bootstrap(
        creator_id="brandon",
        hard_directives=DIRECTIVES,
        canon_self_definition=CANON,
        authority_boundaries=BOUNDARIES,
        secret_key=SECRET,
        storage_path=tmp_path,
    )


class TestRuntimeBootstrap:
    def test_bootstrap_creates_runtime(self):
        runtime = make_runtime()
        assert runtime.identity.creator_id == "brandon"

    def test_identity_stable_after_bootstrap(self):
        runtime = make_runtime()
        runtime.assert_identity_stable()  # should not raise

    def test_wrong_key_triggers_drift_on_construction(self):
        from victor.identity.kernel import IdentityKernel
        kernel = IdentityKernel.create(
            creator_id="brandon",
            hard_directives=DIRECTIVES,
            canon_self_definition=CANON,
            authority_boundaries=BOUNDARIES,
            secret_key=b"original-key",
        )
        with pytest.raises(IdentityViolation):
            VictorRuntime(identity_kernel=kernel, secret_key=b"wrong-key")


class TestInvariant2NarrativeMemory:
    def test_record_episode_and_process_narrative(self):
        runtime = make_runtime()
        ch = runtime.narrative_engine.open_chapter("The Beginning", "First chapter")
        ep = Episode.create("decision", "Left the job.", emotional_weight=-0.5, participants=["brandon"])
        runtime.record_episode(ep)
        event = runtime.process_narrative(
            episodes=[ep],
            meaning="Brandon chose creative freedom over security.",
            chapter_id=ch.id,
            is_turning_point=True,
            wound_or_breakthrough="breakthrough",
            implications=["Needs new income model"],
            promises_or_vows=["Finish the album"],
        )
        assert event.is_turning_point is True
        assert len(runtime.episodic_memory) == 1
        assert len(runtime.narrative_memory) == 1

    def test_narrative_engine_detects_patterns(self):
        runtime = make_runtime()
        ch = runtime.narrative_engine.open_chapter("Pattern Ch", "Desc")
        for _ in range(3):
            ep = Episode.create("observation", "Procrastinated again.")
            runtime.record_episode(ep)
            runtime.process_narrative([ep], "Avoidance pattern.", ch.id, pattern_tags=["avoidance"])
        patterns = runtime.narrative_engine.detect_patterns()
        assert patterns.get("avoidance", 0) == 3


class TestInvariant3GoalInheritance:
    def test_add_and_retrieve_active_missions(self):
        runtime = make_runtime()
        album = IntentNode.create(NodeType.CREATIVE_SEED, "Finish Album", "Music project")
        runtime.add_intent(album)
        assert len(runtime.active_missions()) == 1

    def test_revivable_intents_after_dormant(self):
        runtime = make_runtime()
        album = IntentNode.create(NodeType.CREATIVE_SEED, "Album", "Dormant project")
        runtime.add_intent(album)
        runtime.intent_graph.update_node_status(album.id, "dormant")
        revivable = runtime.revivable_intents()
        assert any(n.id == album.id for n in revivable)

    def test_linked_intents(self):
        runtime = make_runtime()
        mission = IntentNode.create(NodeType.STRATEGIC_MISSION, "Mission", "Top goal")
        project = IntentNode.create(NodeType.PROJECT, "Project", "Advances mission")
        runtime.add_intent(mission)
        runtime.add_intent(project)
        runtime.link_intents(IntentEdge.create(project.id, mission.id, EdgeType.ADVANCES))
        advanced = runtime.intent_graph.advances(project.id)
        assert any(n.id == mission.id for n in advanced)


class TestInvariant4CoAdaptation:
    def test_record_interaction_and_analyse(self):
        runtime = make_runtime()
        for _ in range(3):
            runtime.record_interaction(InteractionRecord.create(
                InterventionType.CHALLENGE,
                "Challenged avoidance pattern.",
                outcome=InterventionOutcome.BREAKTHROUGH,
            ))
        runtime.record_interaction(InteractionRecord.create(
            InterventionType.ADVICE,
            "Gave routine advice.",
            outcome=InterventionOutcome.IGNORED,
        ))
        runtime.record_interaction(InteractionRecord.create(
            InterventionType.ADVICE,
            "Gave more advice.",
            outcome=InterventionOutcome.IGNORED,
        ))
        runtime.record_interaction(InteractionRecord.create(
            InterventionType.ADVICE,
            "Gave even more advice.",
            outcome=InterventionOutcome.IGNORED,
        ))
        best = runtime.best_intervention()
        assert best == InterventionType.CHALLENGE


class TestInvariant5ReflectionSelfCorrection:
    def test_simulate_returns_recommendation(self):
        runtime = make_runtime()
        branches = [
            SimulationBranch.create(
                "Stay the course", 0.8, 0.1, 0.9, 0.05, 0.95, 0.3, 0.85
            ),
            SimulationBranch.create(
                "Abandon project", 0.2, 0.8, 0.3, 0.7, 0.1, 0.1, 0.5
            ),
        ]
        result = runtime.simulate(branches)
        assert result.recommended_branch_id == branches[0].id
        assert result.identity_safe is True

    def test_reflect_returns_quality_score(self):
        runtime = make_runtime()
        report = runtime.reflect(
            "Suggested structured morning routine.",
            reduced_confusion=True,
            strengthened_discipline=True,
            preserved_intent=True,
            advanced_long_arc=True,
        )
        assert report["quality_score"] == pytest.approx(1.0)


class TestInvariant6ContinuityUnderRupture:
    def test_checkpoint_and_restore(self, tmp_path: Path):
        runtime = make_runtime(tmp_path)
        ch = runtime.narrative_engine.open_chapter("Pre-rupture", "Before interruption")
        ep = Episode.create("conversation", "Important talk.")
        runtime.record_episode(ep)
        runtime.process_narrative([ep], "This mattered.", ch.id)
        album = IntentNode.create(NodeType.PROJECT, "Album", "Finish it")
        runtime.add_intent(album)

        cp = runtime.checkpoint()
        assert cp.id

        # Restore into a fresh runtime instance sharing the same persistence layer
        runtime2 = make_runtime(tmp_path)
        runtime2.restore(cp.id)

        assert len(runtime2.episodic_memory) == 1
        assert len(runtime2.narrative_memory) == 1
        assert len(runtime2.intent_graph) == 1

    def test_restore_verifies_identity(self, tmp_path: Path):
        runtime = make_runtime(tmp_path)
        cp = runtime.checkpoint()
        # Should pass without raising
        runtime.restore(cp.id)
        runtime.assert_identity_stable()

    def test_checkpoint_lineage_grows(self, tmp_path: Path):
        runtime = make_runtime(tmp_path)
        runtime.checkpoint()
        runtime.checkpoint()
        runtime.checkpoint()
        assert len(runtime.persistence.lineage()) == 3

    def test_constitutive_memory_survives_checkpoint(self, tmp_path: Path):
        runtime = make_runtime(tmp_path)
        rec = ConstitutiveRecord.create(
            ConstitutiveRecordType.VOW, "Finish the album.", "brandon"
        )
        runtime.constitutive_memory.commit(rec)
        cp = runtime.checkpoint()

        runtime2 = make_runtime(tmp_path)
        runtime2.restore(cp.id)
        assert len(runtime2.constitutive_memory) == 1
        assert runtime2.constitutive_memory.verify_all() is True
