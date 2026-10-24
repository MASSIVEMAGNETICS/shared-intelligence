"""Scheduled-path regression tests: no external GitHub token or network required."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from maintenance_decision import select_decision, write_decision


def test_empty_sync_yields_explicit_no_action_receipt():
    result = select_decision({"decision": None}, {"open_loops": 0})
    assert result["status"] == "NO_ACTIONABLE_OBJECTIVES"


def test_selected_decision_preserved_without_rescoring():
    selected = {"objective_id": "github:repo:pr:3", "state": "BLOCKED", "score": 4.5}
    assert select_decision({"decision": selected}, {"open_loops": 1}) == selected


@pytest.mark.parametrize("sync,status", [
    ({}, {"open_loops": 0}),
    ({"decision": None}, {"open_loops": 1}),
    ({"decision": {"objective_id": "a"}}, {"open_loops": 0}),
    ({"decision": {"objective_id": "  "}}, {"open_loops": 1}),
    ({"decision": "garbage"}, {"open_loops": 1}),
    ({"decision": None}, {"open_loops": True}),
    ({"decision": None}, {"open_loops": -1}),
])
def test_invalid_snapshots_fail_closed(sync, status):
    with pytest.raises(ValueError):
        select_decision(sync, status)


def test_atomic_output_and_no_mutation_of_inputs(tmp_path):
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "out" / "next.json"
    sync.write_text('{"decision": null}')
    status.write_text('{"open_loops": 0}')
    assert write_decision(sync, status, output)["status"] == "NO_ACTIONABLE_OBJECTIVES"
    assert json.loads(output.read_text())["status"] == "NO_ACTIONABLE_OBJECTIVES"
    assert sync.read_text() == '{"decision": null}'
    assert status.read_text() == '{"open_loops": 0}'
    assert not list(output.parent.glob("*.tmp"))


def test_failed_input_preserves_existing_receipt(tmp_path):
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "next.json"
    output.write_text('previous good receipt\n')
    sync.write_text('{"decision": null}')
    status.write_text('{"open_loops": 2}')
    with pytest.raises(ValueError):
        write_decision(sync, status, output)
    assert output.read_text() == 'previous good receipt\n'


def test_cli_succeeds_for_empty_queue(tmp_path):
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "next.json"
    sync.write_text('{"decision": null}')
    status.write_text('{"open_loops": 0}')
    script = Path(__file__).resolve().parents[1] / "maintenance_decision.py"
    result = subprocess.run([sys.executable, str(script), "--sync", str(sync),
                             "--status", str(status), "--output", str(output)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["status"] == "NO_ACTIONABLE_OBJECTIVES"


def test_cli_fails_closed_on_malformed_json(tmp_path):
    sync = tmp_path / "sync.json"
    status = tmp_path / "status.json"
    output = tmp_path / "next.json"
    sync.write_text('{')
    status.write_text('{"open_loops": 0}')
    script = Path(__file__).resolve().parents[1] / "maintenance_decision.py"
    result = subprocess.run([sys.executable, str(script), "--sync", str(sync),
                             "--status", str(status), "--output", str(output)],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert not output.exists()
