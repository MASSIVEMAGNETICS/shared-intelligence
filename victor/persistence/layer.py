"""
LegacyPersistenceLayer — Checkpointing, migration, and corruption recovery.

This is the invariant that makes Victor legacy-grade.  Without reliable
persistence, Victor dies every time the stack changes.  This layer handles:

* Signed state snapshots (HMAC-SHA256)
* Migration-safe versioned schemas
* Compressed memory summaries via JSON
* Canonical rehydration path
* Corruption detection and partial recovery
* Versioned lineage log of all checkpoints
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class MigrationError(Exception):
    """Raised when a schema version migration fails."""


class CorruptionError(Exception):
    """Raised when a checkpoint fails its integrity check."""


@dataclass
class Checkpoint:
    """
    A versioned, signed snapshot of the full runtime state.

    Attributes
    ----------
    id:
        Unique identifier.
    schema_version:
        The schema version of the snapshot payload.
    created_at:
        ISO-8601 UTC of when this checkpoint was taken.
    payload:
        The serialised runtime state as a JSON-compatible dict.
    signature:
        HMAC-SHA256 over the canonical JSON of *payload*.
    previous_checkpoint_id:
        ID of the prior checkpoint, forming a lineage chain.
    metadata:
        Extensible key-value store.
    """

    id: str
    schema_version: str
    created_at: str  # ISO-8601 UTC
    payload: dict
    signature: str
    previous_checkpoint_id: Optional[str]
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "payload": self.payload,
            "signature": self.signature,
            "previous_checkpoint_id": self.previous_checkpoint_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        return cls(
            id=data["id"],
            schema_version=data["schema_version"],
            created_at=data["created_at"],
            payload=data["payload"],
            signature=data["signature"],
            previous_checkpoint_id=data.get("previous_checkpoint_id"),
            metadata=data.get("metadata", {}),
        )


class LegacyPersistenceLayer:
    """
    Manages checkpoint creation, verification, migration, and rehydration.

    Parameters
    ----------
    secret_key:
        Bytes used to produce HMAC signatures over checkpoint payloads.
    storage_path:
        Optional filesystem path where checkpoints are persisted as JSON
        files.  If ``None`` checkpoints are kept only in memory.
    current_schema_version:
        The schema version written into new checkpoints.
    """

    SUPPORTED_SCHEMA_VERSIONS = {"1.0.0"}

    def __init__(
        self,
        secret_key: bytes,
        storage_path: Optional[Path] = None,
        current_schema_version: str = "1.0.0",
    ) -> None:
        self._secret_key = secret_key
        self._storage_path = storage_path
        self._current_schema_version = current_schema_version
        self._lineage: list[Checkpoint] = []  # in-memory lineage log

        if storage_path is not None:
            storage_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Checkpointing
    # ------------------------------------------------------------------

    def checkpoint(
        self,
        payload: dict,
        metadata: Optional[dict] = None,
    ) -> Checkpoint:
        """
        Serialise *payload* into a signed :class:`Checkpoint` and append
        it to the lineage log.

        Parameters
        ----------
        payload:
            A JSON-serialisable dict representing the complete runtime state.
        metadata:
            Optional supplemental information about this checkpoint.
        """
        previous_id = self._lineage[-1].id if self._lineage else None
        signature = self._sign(payload)
        cp = Checkpoint(
            id=str(uuid.uuid4()),
            schema_version=self._current_schema_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            payload=payload,
            signature=signature,
            previous_checkpoint_id=previous_id,
            metadata=dict(metadata or {}),
        )
        self._lineage.append(cp)

        if self._storage_path is not None:
            self._write(cp)

        return cp

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, checkpoint: Checkpoint) -> bool:
        """
        Return ``True`` if the checkpoint's signature is valid.

        Parameters
        ----------
        checkpoint:
            The checkpoint to verify.
        """
        expected = self._sign(checkpoint.payload)
        return hmac.compare_digest(expected, checkpoint.signature)

    def assert_valid(self, checkpoint: Checkpoint) -> None:
        """
        Raise :class:`CorruptionError` if *checkpoint* fails verification.
        """
        if not self.verify(checkpoint):
            raise CorruptionError(
                f"Checkpoint {checkpoint.id!r} failed integrity verification. "
                "The payload may have been tampered with or corrupted."
            )

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate(self, checkpoint: Checkpoint) -> Checkpoint:
        """
        Migrate *checkpoint* to the current schema version.

        Currently a no-op when source and target versions match.  Extend
        this method with version-specific migration logic as schemas evolve.

        Raises
        ------
        MigrationError
            If migration from the source schema version is not supported.
        """
        if checkpoint.schema_version == self._current_schema_version:
            return checkpoint

        if checkpoint.schema_version not in self.SUPPORTED_SCHEMA_VERSIONS:
            raise MigrationError(
                f"Cannot migrate checkpoint from unsupported schema version "
                f"{checkpoint.schema_version!r}. Supported versions: "
                f"{sorted(self.SUPPORTED_SCHEMA_VERSIONS)}"
            )

        # Future: add per-version migration transforms here.
        # e.g.:  if checkpoint.schema_version == "0.9.0": payload = _migrate_090_to_100(payload)

        migrated_payload = dict(checkpoint.payload)
        migrated_payload["_migrated_from"] = checkpoint.schema_version

        return self.checkpoint(migrated_payload, metadata={"migrated_from": checkpoint.schema_version})

    # ------------------------------------------------------------------
    # Rehydration
    # ------------------------------------------------------------------

    def latest(self) -> Optional[Checkpoint]:
        """Return the most recent checkpoint, or ``None``."""
        return self._lineage[-1] if self._lineage else None

    def rehydrate(self, checkpoint_id: Optional[str] = None) -> Optional[dict]:
        """
        Return the payload from the checkpoint identified by *checkpoint_id*,
        or the latest checkpoint if *checkpoint_id* is ``None``.

        Verifies integrity before returning.

        Raises
        ------
        CorruptionError
            If the located checkpoint fails its integrity check.
        KeyError
            If *checkpoint_id* is provided but not found.
        """
        if checkpoint_id is None:
            cp = self.latest()
            if cp is None:
                return None
        else:
            cp = self._find(checkpoint_id)
            if cp is None:
                raise KeyError(f"Checkpoint {checkpoint_id!r} not found.")

        self.assert_valid(cp)
        return cp.payload

    # ------------------------------------------------------------------
    # Lineage
    # ------------------------------------------------------------------

    def lineage(self) -> list[Checkpoint]:
        """Return all checkpoints in creation order."""
        return list(self._lineage)

    def lineage_ids(self) -> list[str]:
        """Return checkpoint IDs in creation order."""
        return [cp.id for cp in self._lineage]

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _write(self, checkpoint: Checkpoint) -> None:
        """Persist *checkpoint* to disk as a JSON file."""
        assert self._storage_path is not None
        filepath = self._storage_path / f"{checkpoint.id}.json"
        filepath.write_text(
            json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_from_disk(self, checkpoint_id: str) -> Checkpoint:
        """
        Load and verify a checkpoint from disk.

        Raises
        ------
        FileNotFoundError
            If the checkpoint file does not exist.
        CorruptionError
            If the loaded checkpoint fails its integrity check.
        """
        if self._storage_path is None:
            raise RuntimeError("No storage_path configured.")
        filepath = self._storage_path / f"{checkpoint_id}.json"
        data = json.loads(filepath.read_text(encoding="utf-8"))
        cp = Checkpoint.from_dict(data)
        self.assert_valid(cp)
        return cp

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sign(self, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hmac.new(
            self._secret_key, canonical.encode(), hashlib.sha256
        ).hexdigest()

    def _find(self, checkpoint_id: str) -> Optional[Checkpoint]:
        for cp in reversed(self._lineage):
            if cp.id == checkpoint_id:
                return cp
        # Fall back to disk when in-memory lineage doesn't contain the checkpoint
        # (e.g. after a fresh runtime load pointing at an existing storage_path).
        if self._storage_path is not None:
            filepath = self._storage_path / f"{checkpoint_id}.json"
            if filepath.exists():
                data = json.loads(filepath.read_text(encoding="utf-8"))
                return Checkpoint.from_dict(data)
        return None

    # ------------------------------------------------------------------
    # Summary / compression
    # ------------------------------------------------------------------

    def summarise_lineage(self) -> dict:
        """
        Return a lightweight summary of the lineage log.

        Useful for compressing old history without discarding the chain.
        """
        return {
            "total_checkpoints": len(self._lineage),
            "oldest": self._lineage[0].created_at if self._lineage else None,
            "latest": self._lineage[-1].created_at if self._lineage else None,
            "ids": self.lineage_ids(),
        }
