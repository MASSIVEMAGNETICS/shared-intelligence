"""Guard the maintenance workflows against floating GitHub Actions references."""

from __future__ import annotations

import re
from pathlib import Path


WORKFLOWS = (
    Path(".github/workflows/daily-empire-maintenance.yml"),
    Path(".github/workflows/bando-driver-ci.yml"),
)
ACTION_REFERENCE = re.compile(r"^\\s*uses:\\s*([^\\s#]+)", re.MULTILINE)
IMMUTABLE_COMMIT = re.compile(r"[0-9a-f]{40}\\Z")


def test_maintenance_workflows_pin_actions_to_full_commit_shas() -> None:
    for workflow in WORKFLOWS:
        content = workflow.read_text(encoding="utf-8")
        references = ACTION_REFERENCE.findall(content)
        assert references, f"{workflow} contains no action references"

        for reference in references:
            if reference.startswith("./"):
                continue
            action, separator, revision = reference.rpartition("@")
            assert separator, f"{workflow}: action reference lacks a revision: {reference}"
            assert action, f"{workflow}: action reference lacks an action name: {reference}"
            assert IMMUTABLE_COMMIT.fullmatch(revision), (
                f"{workflow}: {action} must be pinned to a 40-character commit SHA, "
                f"not {revision!r}"
            )
