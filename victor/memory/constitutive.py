"""
ConstitutiveMemory — The third and most critical layer of Victor's memory.

Constitutive memory stores identity laws, vows, creator-bond declarations,
and hard missions — the things Victor must *refuse to lose*.  Unlike
episodic or narrative records, constitutive records are **append-only and
immutable once committed**.  They cannot be silently overwritten.

It answers the question: **what must not change?**
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ConstitutiveRecordType(str, Enum):
    """Classification of constitutive records."""

    VOW = "vow"
    DIRECTIVE = "directive"
    IDENTITY_LAW = "identity_law"
    CREATOR_BOND = "creator_bond"
    MISSION = "mission"


@dataclass(frozen=True)
class ConstitutiveRecord:
    """
    An immutable constitutive memory record.

    These records define what Victor is at its core.  Each record is
    content-addressed: the ``content_hash`` is derived solely from the
    record content so that any tampering is detectable.

    Attributes
    ----------
    id:
        Unique identifier.
    record_type:
        Semantic category (see :class:`ConstitutiveRecordType`).
    content:
        The full statement of the vow, directive, law, bond, or mission.
    author:
        Who authored this record (typically ``creator_id`` or ``"victor"``).
    content_hash:
        SHA-256 of ``content`` for tamper detection.
    created_at:
        ISO-8601 UTC timestamp.
    supersedes:
        Optional ID of a previous constitutive record that this one
        formally extends or clarifies (never silently replaces).
    """

    id: str
    record_type: ConstitutiveRecordType
    content: str
    author: str
    content_hash: str
    created_at: str  # ISO-8601 UTC
    supersedes: Optional[str]  # ID of superseded record, if any

    @classmethod
    def create(
        cls,
        record_type: ConstitutiveRecordType,
        content: str,
        author: str,
        supersedes: Optional[str] = None,
    ) -> "ConstitutiveRecord":
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return cls(
            id=str(uuid.uuid4()),
            record_type=record_type,
            content=content,
            author=author,
            content_hash=content_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            supersedes=supersedes,
        )

    def verify_integrity(self) -> bool:
        """Return ``True`` if the stored hash matches the content."""
        return hashlib.sha256(self.content.encode()).hexdigest() == self.content_hash

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "record_type": self.record_type.value,
            "content": self.content,
            "author": self.author,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "supersedes": self.supersedes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstitutiveRecord":
        return cls(
            id=data["id"],
            record_type=ConstitutiveRecordType(data["record_type"]),
            content=data["content"],
            author=data["author"],
            content_hash=data["content_hash"],
            created_at=data["created_at"],
            supersedes=data.get("supersedes"),
        )


class ConstitutiveMemory:
    """
    Append-only store of :class:`ConstitutiveRecord` instances.

    Records are *never deleted or silently overwritten*.  Supersession is
    handled by linking new records to the IDs they extend, preserving the
    full lineage.
    """

    def __init__(self) -> None:
        self._records: list[ConstitutiveRecord] = []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def commit(self, record: ConstitutiveRecord) -> None:
        """
        Append a constitutive record.

        Raises
        ------
        ValueError
            If a record with the same ``id`` already exists (no silent
            overwrites).
        RuntimeError
            If the record's ``content_hash`` does not match the content.
        """
        if not record.verify_integrity():
            raise RuntimeError(
                f"Constitutive record {record.id!r} failed integrity check. "
                "The content hash does not match the content."
            )
        for existing in self._records:
            if existing.id == record.id:
                raise ValueError(
                    f"Constitutive record {record.id!r} already committed. "
                    "Constitutive records are immutable and append-only."
                )
        self._records.append(record)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all(self) -> list[ConstitutiveRecord]:
        return list(self._records)

    def by_type(self, record_type: ConstitutiveRecordType) -> list[ConstitutiveRecord]:
        return [r for r in self._records if r.record_type == record_type]

    def vows(self) -> list[ConstitutiveRecord]:
        return self.by_type(ConstitutiveRecordType.VOW)

    def directives(self) -> list[ConstitutiveRecord]:
        return self.by_type(ConstitutiveRecordType.DIRECTIVE)

    def identity_laws(self) -> list[ConstitutiveRecord]:
        return self.by_type(ConstitutiveRecordType.IDENTITY_LAW)

    def missions(self) -> list[ConstitutiveRecord]:
        return self.by_type(ConstitutiveRecordType.MISSION)

    def get(self, record_id: str) -> Optional[ConstitutiveRecord]:
        for r in self._records:
            if r.id == record_id:
                return r
        return None

    def lineage_of(self, record_id: str) -> list[ConstitutiveRecord]:
        """
        Trace the full supersession lineage of a record back to its root.

        Returns the chain in order from the given record back to the
        oldest ancestor (root has no ``supersedes``).
        """
        chain: list[ConstitutiveRecord] = []
        current_id: Optional[str] = record_id
        seen: set[str] = set()
        while current_id is not None:
            if current_id in seen:
                break  # guard against cycles
            seen.add(current_id)
            record = self.get(current_id)
            if record is None:
                break
            chain.append(record)
            current_id = record.supersedes
        return chain

    def verify_all(self) -> bool:
        """Return ``True`` if every stored record passes its integrity check."""
        return all(r.verify_integrity() for r in self._records)

    def __len__(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"records": [r.to_dict() for r in self._records]}

    @classmethod
    def from_dict(cls, data: dict) -> "ConstitutiveMemory":
        mem = cls()
        for raw in data.get("records", []):
            mem.commit(ConstitutiveRecord.from_dict(raw))
        return mem
