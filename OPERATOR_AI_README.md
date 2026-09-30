# Project Operator AI

Status: **candidate bootstrap / unmerged / not deployed**

Branch: `operator-ai-bootstrap`

Base: reviewed BANDO_DRIVER head `189fedfafef04120c40fb3721619e74aa8a76ec2`

## Objective

Build a persistent, governed enterprise operator that can maintain goals and business state, identify the highest-value authorized action, execute within bounded capability leases, independently observe the result, verify it, write a tamper-evident receipt, commit the reality event, rebuild projections, and continue.

This bootstrap deliberately starts with the Empire's current promotion/convergence bottleneck rather than a synthetic business demo.

## Inherited invariants

- WIP <= 3.
- Human STOP fails closed.
- Tier-3 promotion requires explicit human approval pinned to repository + PR + exact SHA.
- A changed SHA invalidates the approval.
- Capabilities are scoped, time-bounded, revocable, and resource-bounded.
- Durable state uses crash-safe atomic replacement.
- Reality events are append-only and SHA-256 chained in SQLite WAL.
- Completion requires an observation and verification receipt.
- Candidate does not mean merged, deployed, live, or monetized.
- Operator AI never self-expands its authority.

## Verification

Run:

```bash
python -m unittest discover -s tests -v
python -m operator_ai.bootstrap_empire
```

Local bootstrap verification before commit: **8/8 tests passed**.

## Promotion boundary

This branch is an implementation candidate only. No merge, deployment, or production promotion is implied by the existence of these files or passing local tests.
