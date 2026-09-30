#!/usr/bin/env python3
from __future__ import annotations

import json

from operator_ai.core import DecisionCandidate, OperatorEngine, OperatorGovernor, Task


BOOTSTRAP_TASKS = {
    "PROMOTE-BANDO-DRIVER": Task(
        task_id="PROMOTE-BANDO-DRIVER",
        objective_id="EMPIRE-CONVERGENCE",
        title="Promote shared-intelligence PR #2 at reviewed exact head",
        authority_class=3,
        required_capability="github.merge_pull_request",
        resource="MASSIVEMAGNETICS/shared-intelligence#2",
        terminal_condition="merged exact reviewed SHA and post-merge branch observed",
        acceptance_test="merge target SHA equals approved SHA and repository reports merged state",
    ),
    "PROMOTE-VICTOROS-17": Task(
        task_id="PROMOTE-VICTOROS-17",
        objective_id="EMPIRE-CONVERGENCE",
        title="Promote victorOS PR #17 after exact-head recheck",
        authority_class=3,
        required_capability="github.merge_pull_request",
        resource="MASSIVEMAGNETICS/victorOS#17",
        terminal_condition="merged verified repair and post-merge observation recorded",
        acceptance_test="approved exact head merged with required CI/review still green",
    ),
    "PROMOTE-SUNOKILLER-4": Task(
        task_id="PROMOTE-SUNOKILLER-4",
        objective_id="EMPIRE-CONVERGENCE",
        title="Promote SUNOKILLER PR #4 at reviewed exact head",
        authority_class=3,
        required_capability="github.merge_pull_request",
        resource="MASSIVEMAGNETICS/SUNOKILLER#4",
        terminal_condition="merged exact reviewed SHA and post-merge branch observed",
        acceptance_test="merge target SHA equals approved SHA and repository reports merged state",
    ),
}

CANDIDATES = [
    DecisionCandidate("C-BANDO", "PROMOTE-BANDO-DRIVER", 100, 0.95, 1.00, 1.00, 0, 5, 5),
    DecisionCandidate("C-VOS17", "PROMOTE-VICTOROS-17", 90, 0.90, 0.95, 1.00, 0, 5, 5),
    DecisionCandidate("C-SUNO4", "PROMOTE-SUNOKILLER-4", 80, 0.95, 0.85, 0.90, 0, 6, 6),
]


def main() -> int:
    governor = OperatorGovernor(max_wip=3)
    engine = OperatorEngine(governor)

    ranked = engine.rank(CANDIDATES)
    for candidate in ranked[:3]:
        governor.admit(BOOTSTRAP_TASKS[candidate.task_id])

    output = {
        "status": "BLOCKED_HUMAN",
        "objective": "EMPIRE-CONVERGENCE",
        "wip_limit": governor.max_wip,
        "active_wip": [task.task_id for task in governor.active_tasks],
        "smallest_next_human_decision": {
            "repository": "MASSIVEMAGNETICS/shared-intelligence",
            "pull_request": 2,
            "exact_sha": "189fedfafef04120c40fb3721619e74aa8a76ec2",
            "instruction": "Approve or reject promotion of this exact immutable target. A changed head invalidates approval.",
        },
        "note": "This bootstrap script never merges, deploys, or fabricates promotion. It only reconstructs and governs the decision boundary.",
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
