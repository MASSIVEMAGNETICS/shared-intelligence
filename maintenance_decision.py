"""Fail-closed, review-only rendering of the BANDO_DRIVER sync decision.

Consumes the existing sync/status snapshots; never changes the registry or activates work.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def select_decision(sync: Any, status: Any) -> dict[str, Any]:
    """Return the authoritative decision or a deliberate empty-queue receipt."""
    if not isinstance(sync, dict) or "decision" not in sync:
        raise ValueError("sync.json missing authoritative decision field")
    if not isinstance(status, dict) or type(status.get("open_loops")) is not int:
        raise ValueError("status.json missing integer open_loops")
    count = status["open_loops"]
    if count < 0:
        raise ValueError("status.json open_loops cannot be negative")

    decision = sync["decision"]
    if decision is None:
        if count != 0:
            raise ValueError("missing decision despite open objectives")
        return {
            "status": "NO_ACTIONABLE_OBJECTIVES",
            "reason": "no open objectives in synchronized registry",
        }
    if not isinstance(decision, dict):
        raise ValueError("invalid non-empty decision")
    objective_id = decision.get("objective_id")
    if not isinstance(objective_id, str) or not objective_id.strip():
        raise ValueError("decision missing non-empty objective_id")
    if count == 0:
        raise ValueError("decision present despite zero open objectives")
    return decision


def write_decision(sync_path: Path, status_path: Path, output_path: Path) -> dict[str, Any]:
    """Validate both inputs before atomically replacing the output artifact."""
    sync = json.loads(sync_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    decision = select_decision(sync, status)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(decision, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", type=Path, default=Path("maintenance-output/sync.json"))
    parser.add_argument("--status", type=Path, default=Path("maintenance-output/status.json"))
    parser.add_argument("--output", type=Path, default=Path("maintenance-output/next.json"))
    args = parser.parse_args()
    try:
        write_decision(args.sync, args.status, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"maintenance decision failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
