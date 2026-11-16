import json
import subprocess
import sys
from pathlib import Path

import pytest

from maintenance_plan import build_review_plan, write_review_plan


def _decision(objective_id="github:MASSIVEMAGNETICS/dev-ville:pr:41", state="BLOCKED"):
    return {
        "objective_id": objective_id,
        "title": "Dev-Ville PR #41: serialize Chronos appends",
        "state": state,
        "stage": "VERIFY",
        "score": 3.25,
        "next_action": "Satisfy draft gates for Dev-Ville PR #41",
        "reason": "PR is draft; independent review and owner approval remain required",
        "active_count": 0,
        "max_active": 3,
    }


def test_github_objective_is_bounded_to_one_repository_and_one_pr():
    plan = build_review_plan({"decision": _decision()}, {"open_loops": 1})
    assert plan["status"] == "BLOCKED_NEEDS_REVIEW"
    assert plan["target"] == {
        "type": "github_pull_request",
        "repository": "MASSIVEMAGNETICS/dev-ville",
        "pull_request": 41,
        "url": "https://github.com/MASSIVEMAGNETICS/dev-ville/pull/41",
    }
    assert plan["bounds"] == {
        "max_repositories": 1,
        "max_objectives_total": 1,
        "max_objectives_per_repository": 1,
    }


def test_blocked_objective_never_proposes_writes_or_activation():
    plan = build_review_plan({"decision": _decision()}, {"open_loops": 1})
    assert plan["workflow_authority"] == {
        "registry_mutation": False,
        "activation": False,
        "github_writes": False,
        "merge": False,
        "deployment": False,
        "production_changes": False,
        "secret_or_credential_changes": False,
    }
    assert any("Do not create a branch" in action for action in plan["reviewer_actions"])


def test_unblocked_objective_proposes_only_dated_branch_and_draft_pr_review_path():
    plan = build_review_plan(
        {"decision": _decision(state="QUEUED")},
        {"open_loops": 1},
    )
    assert plan["status"] == "READY_FOR_REVIEW"
    assert any("dated branch" in action and "draft pull request" in action
               for action in plan["reviewer_actions"])
    assert plan["workflow_authority"]["github_writes"] is False
    assert plan["workflow_authority"]["merge"] is False


def test_intent_objective_does_not_forge_github_target():
    plan = build_review_plan(
        {"decision": _decision("intent:mission-123", "ACTIVE")},
        {"open_loops": 1},
    )
    assert plan["target"] == {"type": "intent_graph", "intent_id": "mission-123"}
    assert plan["required_evidence"][0] == "intent graph source record and provenance"


@pytest.mark.parametrize("objective_id", [
    "github:attacker/repo:pr:1",
    "github:MASSIVEMAGNETICS:pr:1",
    "github:MASSIVEMAGNETICS/repo:pr:0",
    "github:MASSIVEMAGNETICS/repo:pr:one",
    "other:repo:1",
    "intent:   ",
])
def test_malformed_or_untrusted_objective_ids_fail_closed(objective_id):
    with pytest.raises(ValueError):
        build_review_plan({"decision": _decision(objective_id, "ACTIVE")}, {"open_loops": 1})


@pytest.mark.parametrize("field,value", [
    ("title", ""),
    ("next_action", None),
    ("stage", "UNKNOWN"),
    ("score", True),
    ("score", float("inf")),
])
def test_malformed_selected_decision_fields_fail_closed(field, value):
    decision = _decision(state="ACTIVE")
    decision[field] = value
    with pytest.raises(ValueError):
        build_review_plan({"decision": decision}, {"open_loops": 1})


def test_empty_queue_remains_an_explicit_no_action_receipt():
    plan = build_review_plan({"decision": None}, {"open_loops": 0})
    assert plan["status"] == "NO_ACTIONABLE_OBJECTIVES"
    assert plan["selection"] is None
    assert plan["target"] is None
    assert plan["bounds"]["max_repositories"] == 1


def test_atomic_output_and_input_snapshots_are_not_mutated(tmp_path):
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "out" / "review-plan.json"
    sync_text = json.dumps({"decision": _decision(state="ACTIVE")})
    status_text = '{"open_loops": 1}'
    sync.write_text(sync_text, encoding="utf-8")
    status.write_text(status_text, encoding="utf-8")

    result = write_review_plan(sync, status, output)

    assert result["status"] == "READY_FOR_REVIEW"
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert sync.read_text(encoding="utf-8") == sync_text
    assert status.read_text(encoding="utf-8") == status_text
    assert not list(output.parent.glob("*.tmp"))


def test_failed_input_preserves_existing_plan(tmp_path):
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "review-plan.json"
    sync.write_text("{}", encoding="utf-8")
    status.write_text('{"open_loops": 1}', encoding="utf-8")
    output.write_text("previous good plan\n", encoding="utf-8")

    with pytest.raises(ValueError):
        write_review_plan(sync, status, output)

    assert output.read_text(encoding="utf-8") == "previous good plan\n"


def test_cli_succeeds_for_selected_objective(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "review-plan.json"
    sync.write_text(json.dumps({"decision": _decision(state="ACTIVE")}), encoding="utf-8")
    status.write_text('{"open_loops": 1}', encoding="utf-8")
    script = root / "maintenance_plan.py"
    result = subprocess.run(
        [sys.executable, str(script), "--sync", str(sync),
         "--status", str(status), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "READY_FOR_REVIEW"


def test_cli_fails_closed_on_malformed_json(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "review-plan.json"
    sync.write_text("{", encoding="utf-8")
    status.write_text('{"open_loops": 0}', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(root / "maintenance_plan.py"),
         "--sync", str(sync), "--status", str(status), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert not output.exists()
