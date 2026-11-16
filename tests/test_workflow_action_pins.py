"""Guard the maintenance workflows against floating actions and excess permissions."""

from __future__ import annotations

import re
from pathlib import Path


WORKFLOWS = (
    Path(".github/workflows/daily-empire-maintenance.yml"),
    Path(".github/workflows/bando-driver-ci.yml"),
)
ACTION_REFERENCE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
IMMUTABLE_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
EXPECTED_PERMISSIONS = {
    WORKFLOWS[0]: {"contents": "read", "pull-requests": "read"},
    WORKFLOWS[1]: {"contents": "read"},
}


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


def _top_level_permissions(content: str, workflow: Path) -> dict[str, str]:
    declarations = re.findall(r"(?m)^( *)permissions\s*:", content)
    assert declarations == [""], (
        f"{workflow}: expected exactly one top-level permissions block and no job overrides"
    )

    lines = content.splitlines()
    start = next(index for index, line in enumerate(lines) if line == "permissions:")
    permissions: dict[str, str] = {}
    for line in lines[start + 1:]:
        if line and not line[0].isspace():
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(read|write|none)", stripped)
        assert match, f"{workflow}: malformed permission entry: {line!r}"
        scope, access = match.groups()
        assert scope not in permissions, f"{workflow}: duplicate permission scope {scope}"
        permissions[scope] = access
    return permissions


def test_maintenance_workflows_use_exact_minimal_read_permissions() -> None:
    for workflow, expected in EXPECTED_PERMISSIONS.items():
        content = workflow.read_text(encoding="utf-8")
        assert _top_level_permissions(content, workflow) == expected, (
            f"{workflow}: permission scopes must remain exactly {expected}"
        )
