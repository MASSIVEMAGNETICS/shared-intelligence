"""Exercise the scheduled BANDO_DRIVER collector with a fake GitHub CLI.

No GitHub credentials, network, branch writes, or production effects are used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPOS = (
    "MASSIVEMAGNETICS/shared-intelligence",
    "MASSIVEMAGNETICS/omni",
    "MASSIVEMAGNETICS/victor_empire",
)

FAKE_GH = '''#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) < 3 or sys.argv[1] != "api":
    sys.exit(2)
endpoint = sys.argv[2]
log_path = os.environ.get("FAKE_GH_CALL_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(endpoint + "\\n")
if endpoint.endswith("/pulls?state=open&per_page=100"):
    repo = endpoint[len("repos/"):].split("/pulls?", 1)[0]
    if os.environ.get("FAKE_GH_DENY_REPO") == repo:
        print("synthetic GitHub access denied", file=sys.stderr)
        sys.exit(1)
    if repo == "MASSIVEMAGNETICS/shared-intelligence" and os.environ.get("FAKE_GH_SCENARIO") == "draft":
        print(json.dumps([[{"number": 3}]]))
    else:
        print("[[]]")
elif endpoint == "repos/MASSIVEMAGNETICS/shared-intelligence/pulls/3":
    print(json.dumps({
        "number": 3,
        "draft": True,
        "mergeable": True,
        "title": "Review-only collector",
        "body": "Requires human approval",
        "labels": [],
        "head": {"sha": "synthetic-sha"},
        "html_url": "https://github.com/MASSIVEMAGNETICS/shared-intelligence/pull/3",
    }))
else:
    print("unexpected GitHub API endpoint: " + endpoint, file=sys.stderr)
    sys.exit(2)
'''


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO_ROOT, env=env, text=True,
                          capture_output=True, check=False, timeout=30)


def _fixture(tmp_path: Path, scenario: str, denied_repo: str | None = None):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
        "FAKE_GH_SCENARIO": scenario,
        "FAKE_GH_CALL_LOG": str(tmp_path / "gh_calls.txt"),
        "GH_TOKEN": "synthetic-test-token",
    })
    if denied_repo:
        env["FAKE_GH_DENY_REPO"] = denied_repo
    registry = tmp_path / "registry.json"
    sync_command = [sys.executable, str(REPO_ROOT / "bando_driver.py"),
                    "--registry", str(registry), "sync"]
    for repo in REPOS:
        sync_command.extend(["--github-repo", repo])
    sync_command.append("--no-activate")
    return env, registry, sync_command


def _collect(tmp_path: Path, scenario: str):
    env, registry, sync_command = _fixture(tmp_path, scenario)
    sync = _run(sync_command, env)
    assert sync.returncode == 0, sync.stderr
    sync_path = tmp_path / "sync.json"
    sync_path.write_text(sync.stdout, encoding="utf-8")
    status = _run([sys.executable, str(REPO_ROOT / "bando_driver.py"),
                   "--registry", str(registry), "status"], env)
    assert status.returncode == 0, status.stderr
    status_path = tmp_path / "status.json"
    status_path.write_text(status.stdout, encoding="utf-8")
    output = tmp_path / "next.json"
    render = _run([sys.executable, str(REPO_ROOT / "maintenance_decision.py"),
                   "--sync", str(sync_path), "--status", str(status_path),
                   "--output", str(output)], env)
    assert render.returncode == 0, render.stderr
    calls = (tmp_path / "gh_calls.txt").read_text(encoding="utf-8")
    for repo in REPOS:
        assert f"repos/{repo}/pulls?state=open&per_page=100" in calls
    return json.loads(sync.stdout), json.loads(status.stdout), json.loads(output.read_text())


def test_scheduled_collection_empty_queue_is_success(tmp_path):
    sync, status, decision = _collect(tmp_path, "empty")
    assert sync["decision"] is None
    assert status["open_loops"] == 0
    assert status["active_count"] == 0
    assert decision["status"] == "NO_ACTIONABLE_OBJECTIVES"


def test_scheduled_collection_draft_pr_remains_blocked(tmp_path):
    sync, status, decision = _collect(tmp_path, "draft")
    assert sync["decision"]["objective_id"] == "github:MASSIVEMAGNETICS/shared-intelligence:pr:3"
    assert status["counts"]["BLOCKED"] == 1
    assert status["active_count"] == 0
    assert decision["state"] == "BLOCKED"
    assert decision["objective_id"] == sync["decision"]["objective_id"]


def test_scheduled_collection_denied_repository_fails_without_partial_registry(tmp_path):
    env, registry, command = _fixture(tmp_path, "draft", "MASSIVEMAGNETICS/omni")
    result = _run(command, env)
    assert result.returncode != 0
    assert "synthetic GitHub access denied" in result.stderr
    assert not registry.exists(), "partial authoritative snapshots must not be committed"
    assert not result.stdout.strip(), "a failed collection must not emit a success snapshot"
