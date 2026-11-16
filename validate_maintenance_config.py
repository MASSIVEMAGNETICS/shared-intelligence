from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_REPOSITORY_OWNER = "MASSIVEMAGNETICS"


class ConfigError(ValueError):
    """Raised when the review-only maintenance source config is unsafe."""


def validate_config(raw: Any, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Validate the scheduled collector config without coercing JSON types."""
    if not isinstance(raw, dict):
        raise ConfigError("top-level config must be a JSON object")

    version = raw.get("schema_version")
    if type(version) is not int or version != 1:
        raise ConfigError("schema_version must be the integer 1")

    repositories = raw.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise ConfigError("repositories must be a non-empty JSON array")

    seen: set[str] = set()
    for index, repository in enumerate(repositories):
        if not isinstance(repository, str):
            raise ConfigError(f"repositories[{index}] must be a string")
        if repository != repository.strip() or repository.count("/") != 1:
            raise ConfigError(f"repositories[{index}] must be an exact owner/name value")
        owner, name = repository.split("/", 1)
        if not owner or not name or any(ch.isspace() for ch in repository):
            raise ConfigError(f"repositories[{index}] must be an exact owner/name value")
        if owner.casefold() != EXPECTED_REPOSITORY_OWNER.casefold():
            raise ConfigError(
                f"repositories[{index}] owner must be {EXPECTED_REPOSITORY_OWNER}"
            )
        canonical_repository = repository.casefold()
        if canonical_repository in seen:
            raise ConfigError(
                f"duplicate repository entry (case-insensitive): {repository}"
            )
        seen.add(canonical_repository)

    max_active = raw.get("max_active")
    if type(max_active) is not int or max_active < 1:
        raise ConfigError("max_active must be a positive JSON integer")

    policy = raw.get("policy")
    if not isinstance(policy, dict):
        raise ConfigError("policy must be a JSON object")
    activate_top = policy.get("activate_top")
    if type(activate_top) is not bool:
        raise ConfigError("policy.activate_top must be a JSON boolean")
    if activate_top is not False:
        raise ConfigError("policy.activate_top must be false for the review-only collector")

    snapshot = raw.get("intent_graph_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, str) or not snapshot.strip():
            raise ConfigError("intent_graph_snapshot must be a non-empty path when configured")
        snapshot_path = Path(snapshot)
        if not snapshot_path.is_absolute() and base_dir is not None:
            snapshot_path = base_dir / snapshot_path
        if not snapshot_path.is_file():
            raise ConfigError(f"configured intent graph snapshot does not exist: {snapshot}")

    return raw


def load_config(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read valid JSON config: {exc}") from exc
    return validate_config(raw, base_dir=path.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("bando_maintenance_sources.json"))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"maintenance config rejected: {exc}", file=sys.stderr)
        return 2
    print(
        "valid read-only maintenance config: "
        f"{len(config['repositories'])} repositories; max_active={config['max_active']}; "
        "activation disabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
