"""Create a bounded, review-only work package from the existing BANDO_DRIVER decision.

This renderer does not rescore objectives, mutate the registry, activate work, or write to GitHub.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from maintenance_decision import select_decision

VALID_STAGES = {"DISCOVERY", "BUILD", "VERIFY", "DEPLOY", "SELL", "OBSERVE", "SCALE"}
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")


def _parse_target(objective_id: str) -> dict[str, Any]:
    if objective_id.startswith("github:"):
        payload = objective_id[len("github:"):]
        repository, separator, number_text = payload.rpartition(":pr:")
        if (
            not separator
            or not repository
            or not number_text.isascii()
            or not number_text.isdecimal()
        ):
            raise ValueError("GitHub objective id must be github:OWNER/REPO:pr:NUMBER")
        owner, slash, name = repository.partition("/")
        if (
            not slash
            or not owner
            or not name
            or owner.casefold() != "massivemagnetics"
            or not REPOSITORY_NAME.fullmatch(name)
            or any(ch.isspace() for ch in repository)
        ):
            raise ValueError("GitHub objective repository must be MASSIVEMAGNETICS/REPO")
        number = int(number_text)
        if number < 1:
            raise ValueError("GitHub pull request number must be positive")
        return {
            "type": "github_pull_request",
            "repository": repository,
            "pull_request": number,
            "url": f"https://github.com/{repository}/pull/{number}",
        }

    if objective_id.startswith("intent:"):
        intent_id = objective_id[len("intent:"):].strip()
        if not intent_id:
            raise ValueError("intent objective id must not be empty")
        return {"type": "intent_graph", "intent_id": intent_id}

    raise ValueError("unsupported objective id namespace")


def build_review_plan(sync: Any, status: Any) -> dict[str, Any]:
    """Translate the selected objective into a bounded plan without changing its ranking."""
    decision = select_decision(sync, status)
    bounds = {
        "max_repositories": 1,
        "max_objectives_total": 1,
        "max_objectives_per_repository": 1,
    }
    authority = {
        "registry_mutation": False,
        "activation": False,
        "github_writes": False,
        "merge": False,
        "deployment": False,
        "production_changes": False,
        "secret_or_credential_changes": False,
    }

    if decision.get("status") == "NO_ACTIONABLE_OBJECTIVES":
        return {
            "schema_version": 1,
            "status": "NO_ACTIONABLE_OBJECTIVES",
            "source": "BANDO_DRIVER",
            "reason": decision["reason"],
            "selection": None,
            "target": None,
            "bounds": bounds,
            "workflow_authority": authority,
            "reviewer_actions": [],
            "required_evidence": [],
        }

    objective_id = decision["objective_id"]
    target = _parse_target(objective_id)
    title = decision.get("title")
    next_action = decision.get("next_action")
    stage = decision.get("stage")
    reason = decision.get("reason")
    score = decision.get("score")

    for name, value in (("title", title), ("next_action", next_action), ("reason", reason)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"selected decision {name} must be a non-empty string")
    if not isinstance(stage, str) or stage not in VALID_STAGES:
        raise ValueError("selected decision stage is invalid")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError("selected decision score must be finite")

    state = decision["state"]
    selection = {
        "objective_id": objective_id,
        "title": title,
        "state": state,
        "stage": stage,
        "score": score,
        "next_action": next_action,
        "reason": reason,
    }

    if state == "BLOCKED":
        plan_status = "BLOCKED_NEEDS_REVIEW"
        reviewer_actions = [
            "Inspect the target's documented blocker and the evidence required to clear it.",
            "Record the exact missing evidence, owner decision, or dependency.",
            "Do not create a branch, commit, pull request, merge, deploy, or change production state while blocked.",
        ]
    else:
        plan_status = "READY_FOR_REVIEW"
        reviewer_actions = [
            "Read the target repository README and applicable CONTRIBUTING.md or AGENTS.md instructions.",
            "Inspect the target's current diff, exact head SHA, open review threads, issues, and required checks.",
            "Choose one coherent, testable maintenance objective within the selected repository.",
            "Add targeted regression coverage and run the repository checks that apply.",
            "If a change is justified, use a dated branch and an open draft pull request; update an existing PR when it already covers the same objective.",
            "Stop before merge, deployment, release, or production changes for explicit owner approval.",
        ]

    if target["type"] == "github_pull_request":
        required_evidence = [
            "current PR head SHA and exact-head CI results",
            "review and approval-gate status",
            "targeted regression test results",
            "changed-file list and bounded diff",
            "rollback path",
        ]
    else:
        required_evidence = [
            "intent graph source record and provenance",
            "one testable next action",
            "dependency and blocker evidence",
            "rollback path",
        ]

    return {
        "schema_version": 1,
        "status": plan_status,
        "source": "BANDO_DRIVER",
        "selection": selection,
        "target": target,
        "bounds": bounds,
        "workflow_authority": authority,
        "reviewer_actions": reviewer_actions,
        "required_evidence": required_evidence,
    }


def write_review_plan(sync_path: Path, status_path: Path, output_path: Path) -> dict[str, Any]:
    """Validate inputs and atomically write the review plan, preserving prior output on failure."""
    sync = json.loads(sync_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    plan = build_review_plan(sync, status)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(plan, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", type=Path, default=Path("maintenance-output/sync.json"))
    parser.add_argument("--status", type=Path, default=Path("maintenance-output/status.json"))
    parser.add_argument("--output", type=Path, default=Path("maintenance-output/review-plan.json"))
    args = parser.parse_args()
    try:
        write_review_plan(args.sync, args.status, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"maintenance plan failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
