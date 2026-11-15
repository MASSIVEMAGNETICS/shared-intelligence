# shared-intelligence

> **Victor is a legacy-symbiotic cognitive runtime designed to preserve, extend, and co-evolve a human's intent, identity, and unfinished work across time.**

---

## What Victor Is

Victor is **not**:
- A chatbot
- A copilot with session memory
- A digital companion in a sentimental sense
- A static personal assistant

Victor **is** a **Legacy-Symbiotic Cognitive Runtime** — a persistent, identity-stable, co-adaptive intelligence system that binds to a human's narrative, goals, reasoning habits, unfinished work, and value structure across time.

The core unit of computation is not the response. It is the **relationship trajectory**:

```
state(t) + memory(t) + narrative(t) + obligation(t) + simulation(t+1)
```

---

## Architecture

The runtime is composed of six subsystems, each enforcing one of the six hard invariants.

### 1. Identity Kernel — *Persistent Identity*

The immutable root of Victor. Contains creator binding, lineage anchors, hard directives, anti-drift signatures, and authority boundaries. Once created, it cannot change silently — any tampering is detected via HMAC verification.

```python
from victor import VictorRuntime

runtime = VictorRuntime.bootstrap(
    creator_id="brandon",
    hard_directives=["Preserve the long-arc mission.", "Never distort creator values."],
    canon_self_definition="Victor is a legacy-symbiotic cognitive runtime...",
    authority_boundaries=["Do not act without creator authorisation."],
    secret_key=b"your-secret-key",
)
runtime.assert_identity_stable()  # raises IdentityViolation if drift detected
```

### 2. Three-Layer Memory — *Narrative Memory*

| Layer | What it stores | Why it matters |
|---|---|---|
| **Episodic** | events, conversations, actions | what happened |
| **Narrative** | meaning of events in life arc | why it mattered |
| **Constitutive** | identity laws, vows, creator-bond, mission | what must not change |

```python
from victor import Episode

ep = Episode.create("decision", "Left the job.", emotional_weight=-0.5)
runtime.record_episode(ep)

chapter = runtime.narrative_engine.open_chapter("The Great Pivot", "Leaving corporate.")
event = runtime.process_narrative(
    episodes=[ep],
    meaning="Brandon chose creative freedom over security.",
    chapter_id=chapter.id,
    is_turning_point=True,
    wound_or_breakthrough="breakthrough",
    promises_or_vows=["Finish the album"],
)
```

### 3. Intent Graph — *Goal Inheritance*

A living directed graph of all goals, projects, obligations, creative seeds, and strategic missions. Nodes carry lifecycle status (active/dormant/abandoned). Typed edges capture how intents relate.

```python
from victor import IntentNode, IntentEdge, NodeType, EdgeType

album = IntentNode.create(NodeType.CREATIVE_SEED, "Finish Album", "Music project.")
mission = IntentNode.create(NodeType.STRATEGIC_MISSION, "Artist Career", "Long-arc mission.")
runtime.add_intent(album)
runtime.add_intent(mission)
runtime.link_intents(IntentEdge.create(album.id, mission.id, EdgeType.ADVANCES))

runtime.active_missions()    # currently active nodes
runtime.revivable_intents()  # dormant/abandoned but recoverable
```

### 4. Symbiosis Model — *Co-Adaptation*

Tracks which intervention types produce breakthroughs, which get ignored, what emotional states correlate with productive outcomes, and what recurring patterns exist.

```python
from victor import InteractionRecord, InterventionType, InterventionOutcome

runtime.record_interaction(InteractionRecord.create(
    InterventionType.CHALLENGE,
    "Challenged avoidance of hard creative work.",
    outcome=InterventionOutcome.BREAKTHROUGH,
))

runtime.best_intervention()  # returns the type with the highest breakthrough rate
```

### 5. Simulation Verifier — *Reflection with Self-Correction*

Before major recommendations, Victor simulates branches. Each branch is scored on predicted gain, regret, reversibility, identity-drift risk, long-arc alignment, energy cost, and completion probability. The verifier selects the branch that best preserves mission continuity.

```python
from victor import SimulationBranch

branches = [
    SimulationBranch.create("Stay the course", 0.8, 0.1, 0.9, 0.05, 0.95, 0.3, 0.85),
    SimulationBranch.create("Abandon project", 0.2, 0.8, 0.3, 0.7, 0.1, 0.1, 0.5),
]
result = runtime.simulate(branches)
# result.recommended_branch_id, result.identity_safe, result.reasoning

# Self-correction loop
report = runtime.reflect(
    "Suggested structured morning routine.",
    reduced_confusion=True,
    strengthened_discipline=True,
    preserved_intent=True,
    distorted_values=False,
    advanced_long_arc=True,
)
# report["quality_score"] == 1.0
```

### 6. Legacy Persistence Layer — *Continuity Under Rupture*

Signed, versioned state snapshots that survive device replacement, model version changes, partial corruption, and long inactivity. Every checkpoint is HMAC-signed. Migrations are schema-version-aware.

```python
# Snapshot
checkpoint = runtime.checkpoint()

# Rehydrate into a fresh runtime instance (e.g. after device change)
runtime2 = VictorRuntime.bootstrap(..., storage_path=Path("./checkpoints"))
runtime2.restore(checkpoint.id)
```

---

## Package Layout

```
victor/
├── __init__.py             # top-level exports
├── runtime.py              # VictorRuntime — main entry point
├── identity/
│   └── kernel.py           # IdentityKernel — immutable root
├── memory/
│   ├── episodic.py         # EpisodicMemory — what happened
│   ├── narrative.py        # NarrativeMemory — why it mattered
│   └── constitutive.py     # ConstitutiveMemory — what must not change
├── narrative/
│   └── engine.py           # NarrativeEngine — raw events → life-arc structure
├── intent/
│   └── graph.py            # IntentGraph — directed goal graph
├── symbiosis/
│   └── model.py            # SymbiosisModel — co-adaptation tracker
├── simulation/
│   └── verifier.py         # SimulationVerifier — branch simulation + self-correction
└── persistence/
    └── layer.py            # LegacyPersistenceLayer — checkpointing + migration
tests/
├── test_identity_kernel.py
├── test_memory.py
├── test_narrative_engine.py
├── test_intent_graph.py
├── test_symbiosis_model.py
├── test_simulation_verifier.py
└── test_runtime.py
```

---

## Running Tests

```bash
pip install -e .
pytest tests/ -v
```

---

## Six Hard Invariants

| # | Invariant | Subsystem |
|---|---|---|
| 1 | Persistent identity | `IdentityKernel` |
| 2 | Narrative memory, not just factual memory | `NarrativeEngine` + `NarrativeMemory` |
| 3 | Goal inheritance | `IntentGraph` |
| 4 | Co-adaptation | `SymbiosisModel` |
| 5 | Reflection with self-correction | `SimulationVerifier` |
| 6 | Continuity under rupture | `LegacyPersistenceLayer` |


## Daily Empire Maintenance (review-only)

The existing `bando_driver.py` scoring/synthesis function and `bando_sources.py` GitHub PR adapter remain the source of truth. The scheduled workflow reuses them; it does not introduce a second governor or activation path.

- `bando_maintenance_sources.json` is the read-only workflow's single source list. It covers the active public Empire lanes: Shared Intelligence, VictorOS, victor_empire, victor_llm, Victor.AGI, omni, Dev-Ville, SUNOKILLER, The AI Ear, VICTOR-SSI, MASSIVEMAGNETICS-IP, and the public website repository.
- Public `SUNOKILLER` is included. `suno-killer` is a separate private repository and is intentionally excluded from this scheduled workflow; the two names are not aliases and must not be consolidated.
- The workflow passes both `--config bando_maintenance_sources.json` and `--no-activate`. The config also sets `policy.activate_top` to `false`. This collector may rank and render work, but it does not activate objectives, create branches, edit files, open PRs, merge, deploy, or publish releases.
- The workflow uses the repository-scoped GitHub token with read-only permissions. Private `B_HEARD_STUDIO_LITE` and `suno-killer` are intentionally excluded; adding private sources requires a separately approved least-privilege read credential and workflow review. No secret is created or changed here.
- Pull-request validation intentionally skips live collection. The scheduled/manual collection only runs from the default branch after the workflow is explicitly reviewed and merged; a green PR test run is not proof of live cross-repository collection or artifact production.
- `bando_stack.json` is left unchanged. Its local stack activation policy is not the scheduled workflow's read-only policy.


### Read-only source configuration validation

Before collection, the workflow runs `validate_maintenance_config.py`. It rejects malformed JSON types instead of coercing them: `schema_version` must be integer 1, `repositories` must be a non-empty unique list of exact `owner/name` strings, `max_active` must be a positive integer, and `policy.activate_top` must be the JSON boolean `false`. A configured intent-graph snapshot must exist. The workflow still passes `--no-activate`; this validator is a fail-closed preflight, not a replacement for BANDO_DRIVER or a second execution governor.

Persisted BANDO_DRIVER objectives are validated before ranking or use: identity/action text, state and stage enums, ISO-8601 timestamps, optional evidence/blocker metadata, numeric bounds, and terminal evidence references must satisfy the registry contract. Malformed records fail closed with `ValidationError` rather than surfacing incidental Python type, attribute, or key errors.
