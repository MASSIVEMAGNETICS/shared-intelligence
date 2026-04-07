"""
victor — Legacy-Symbiotic Cognitive Runtime

Victor is a persistent, identity-stable, co-adaptive intelligence system
that binds to a human's narrative, goals, reasoning habits, unfinished work,
and value structure across time.

Doctrine:
    Victor is a legacy-symbiotic cognitive runtime designed to preserve,
    extend, and co-evolve a human's intent, identity, and unfinished work
    across time.
"""

from victor.runtime import VictorRuntime, RuntimeNotInitializedError
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
from victor.persistence.layer import LegacyPersistenceLayer, Checkpoint, MigrationError, CorruptionError

__all__ = [
    # Runtime
    "VictorRuntime",
    "RuntimeNotInitializedError",
    # Identity
    "IdentityKernel",
    "IdentityViolation",
    # Memory
    "EpisodicMemory",
    "Episode",
    "NarrativeMemory",
    "NarrativeEvent",
    "ConstitutiveMemory",
    "ConstitutiveRecord",
    "ConstitutiveRecordType",
    # Narrative
    "NarrativeEngine",
    "LifeArcChapter",
    "TurningPoint",
    # Intent
    "IntentGraph",
    "IntentNode",
    "IntentEdge",
    "NodeType",
    "NodeStatus",
    "EdgeType",
    # Symbiosis
    "SymbiosisModel",
    "InteractionRecord",
    "InterventionType",
    "InterventionOutcome",
    # Simulation
    "SimulationVerifier",
    "SimulationBranch",
    "VerificationResult",
    # Persistence
    "LegacyPersistenceLayer",
    "Checkpoint",
    "MigrationError",
    "CorruptionError",
]
