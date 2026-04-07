"""
IdentityKernel — The immutable root of Victor's persistent identity.

This is the foundational invariant layer. It stores creator binding, lineage
anchors, hard directives, anti-drift signatures, and authority boundaries.
It must remain stable across sessions, hardware changes, and model swaps.

The identity kernel is frozen at creation. Any subsequent check of the kernel
against a stored signature reveals whether identity drift has occurred.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import FrozenSet


class IdentityViolation(Exception):
    """Raised when an operation would violate identity integrity."""


@dataclass(frozen=True)
class IdentityKernel:
    """
    Immutable root of Victor's identity.

    Once created this object must not change. Its ``anti_drift_signature``
    encodes a cryptographic commitment to the core identity fields. Any
    re-derived signature that does not match the stored one signals that
    drift has occurred and the runtime should halt until the operator
    explicitly resolves the discrepancy.

    Attributes
    ----------
    creator_id:
        Stable identifier of the human this runtime is bound to.
    lineage_anchor:
        A deterministic hash of the original creation payload used to
        verify unbroken lineage across rehydrations and migrations.
    hard_directives:
        Immutable behavioural laws that Victor must uphold in every session.
    anti_drift_signature:
        HMAC-SHA256 signature over the canonical identity payload.  Computed
        at creation and re-verified on every load.
    canon_self_definition:
        One-sentence doctrine that defines what Victor fundamentally *is*.
    authority_boundaries:
        Enumeration of what Victor is explicitly *not* authorised to do.
    schema_version:
        Monotonically increasing version that allows migration-safe reads.
    created_at:
        ISO-8601 timestamp (UTC) of kernel creation.
    """

    creator_id: str
    lineage_anchor: str
    hard_directives: FrozenSet[str]
    anti_drift_signature: str
    canon_self_definition: str
    authority_boundaries: FrozenSet[str]
    schema_version: str
    created_at: str  # ISO-8601 UTC string kept as str for frozen-dataclass JSON round-trip

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        creator_id: str,
        hard_directives: list[str],
        canon_self_definition: str,
        authority_boundaries: list[str],
        secret_key: bytes,
        schema_version: str = "1.0.0",
    ) -> "IdentityKernel":
        """
        Construct a new IdentityKernel, computing the lineage anchor and
        anti-drift signature from the supplied secret key.

        Parameters
        ----------
        creator_id:
            Stable identifier of the human this runtime is bound to.
        hard_directives:
            Immutable behavioural laws that Victor must uphold.
        canon_self_definition:
            One-sentence doctrine defining what Victor is.
        authority_boundaries:
            What Victor is explicitly *not* authorised to do.
        secret_key:
            Bytes used to produce the HMAC anti-drift signature.  Must be
            kept confidential and must be identical across all verifications.
        schema_version:
            Semantic version string for migration purposes.
        """
        created_at = datetime.now(timezone.utc).isoformat()

        core_payload = cls._build_canonical_payload(
            creator_id=creator_id,
            hard_directives=sorted(hard_directives),
            canon_self_definition=canon_self_definition,
            authority_boundaries=sorted(authority_boundaries),
            created_at=created_at,
        )

        lineage_anchor = hashlib.sha256(core_payload.encode()).hexdigest()
        anti_drift_signature = hmac.new(
            secret_key, core_payload.encode(), hashlib.sha256
        ).hexdigest()

        return cls(
            creator_id=creator_id,
            lineage_anchor=lineage_anchor,
            hard_directives=frozenset(hard_directives),
            anti_drift_signature=anti_drift_signature,
            canon_self_definition=canon_self_definition,
            authority_boundaries=frozenset(authority_boundaries),
            schema_version=schema_version,
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, secret_key: bytes) -> bool:
        """
        Re-derive the anti-drift signature and compare it to the stored
        value.  Returns ``True`` if no drift is detected.

        Parameters
        ----------
        secret_key:
            The same bytes used during :meth:`create`.
        """
        core_payload = self._build_canonical_payload(
            creator_id=self.creator_id,
            hard_directives=sorted(self.hard_directives),
            canon_self_definition=self.canon_self_definition,
            authority_boundaries=sorted(self.authority_boundaries),
            created_at=self.created_at,
        )
        expected = hmac.new(
            secret_key, core_payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, self.anti_drift_signature)

    def assert_no_drift(self, secret_key: bytes) -> None:
        """
        Raise :class:`IdentityViolation` if drift is detected.

        Parameters
        ----------
        secret_key:
            The same bytes used during :meth:`create`.
        """
        if not self.verify(secret_key):
            raise IdentityViolation(
                "Identity drift detected: anti-drift signature mismatch. "
                "Victor's identity kernel has been tampered with or corrupted."
            )

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the kernel."""
        return {
            "creator_id": self.creator_id,
            "lineage_anchor": self.lineage_anchor,
            "hard_directives": sorted(self.hard_directives),
            "anti_drift_signature": self.anti_drift_signature,
            "canon_self_definition": self.canon_self_definition,
            "authority_boundaries": sorted(self.authority_boundaries),
            "schema_version": self.schema_version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IdentityKernel":
        """Reconstruct an IdentityKernel from a serialised dict."""
        return cls(
            creator_id=data["creator_id"],
            lineage_anchor=data["lineage_anchor"],
            hard_directives=frozenset(data["hard_directives"]),
            anti_drift_signature=data["anti_drift_signature"],
            canon_self_definition=data["canon_self_definition"],
            authority_boundaries=frozenset(data["authority_boundaries"]),
            schema_version=data["schema_version"],
            created_at=data["created_at"],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_canonical_payload(
        creator_id: str,
        hard_directives: list[str],
        canon_self_definition: str,
        authority_boundaries: list[str],
        created_at: str,
    ) -> str:
        """
        Build the deterministic canonical string over which the lineage
        anchor and anti-drift signature are computed.
        """
        payload = {
            "creator_id": creator_id,
            "hard_directives": hard_directives,
            "canon_self_definition": canon_self_definition,
            "authority_boundaries": authority_boundaries,
            "created_at": created_at,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
