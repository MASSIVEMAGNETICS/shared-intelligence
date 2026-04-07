"""Tests for IdentityKernel."""

import pytest
from victor.identity.kernel import IdentityKernel, IdentityViolation

SECRET = b"test-secret-key-for-identity"

DIRECTIVES = [
    "Preserve Brandon's long-arc mission above all else.",
    "Never act against the creator's constitutive values.",
    "Maintain continuity of identity across sessions.",
]

BOUNDARIES = [
    "Do not make decisions that irreversibly harm the creator.",
    "Do not operate without creator authorisation.",
]

CANON = (
    "Victor is a legacy-symbiotic cognitive runtime designed to preserve, "
    "extend, and co-evolve a human's intent, identity, and unfinished work across time."
)


def make_kernel(secret: bytes = SECRET) -> IdentityKernel:
    return IdentityKernel.create(
        creator_id="brandon",
        hard_directives=DIRECTIVES,
        canon_self_definition=CANON,
        authority_boundaries=BOUNDARIES,
        secret_key=secret,
    )


class TestIdentityKernelCreation:
    def test_fields_populated(self):
        kernel = make_kernel()
        assert kernel.creator_id == "brandon"
        assert "Preserve Brandon's long-arc mission above all else." in kernel.hard_directives
        assert kernel.canon_self_definition == CANON
        assert kernel.lineage_anchor  # non-empty
        assert kernel.anti_drift_signature  # non-empty
        assert kernel.schema_version == "1.0.0"
        assert kernel.created_at

    def test_frozen(self):
        kernel = make_kernel()
        with pytest.raises((AttributeError, TypeError)):
            kernel.creator_id = "evil"  # type: ignore[misc]

    def test_hard_directives_are_frozenset(self):
        kernel = make_kernel()
        assert isinstance(kernel.hard_directives, frozenset)

    def test_authority_boundaries_are_frozenset(self):
        kernel = make_kernel()
        assert isinstance(kernel.authority_boundaries, frozenset)


class TestIdentityKernelVerification:
    def test_verify_passes_with_correct_key(self):
        kernel = make_kernel()
        assert kernel.verify(SECRET) is True

    def test_verify_fails_with_wrong_key(self):
        kernel = make_kernel()
        assert kernel.verify(b"wrong-key") is False

    def test_assert_no_drift_passes(self):
        kernel = make_kernel()
        kernel.assert_no_drift(SECRET)  # should not raise

    def test_assert_no_drift_raises_on_tampered_signature(self):
        kernel = make_kernel()
        # Manually construct a kernel with a bad signature
        tampered = IdentityKernel(
            creator_id=kernel.creator_id,
            lineage_anchor=kernel.lineage_anchor,
            hard_directives=kernel.hard_directives,
            anti_drift_signature="badsignature",
            canon_self_definition=kernel.canon_self_definition,
            authority_boundaries=kernel.authority_boundaries,
            schema_version=kernel.schema_version,
            created_at=kernel.created_at,
        )
        with pytest.raises(IdentityViolation):
            tampered.assert_no_drift(SECRET)

    def test_different_secrets_produce_different_signatures(self):
        k1 = make_kernel(b"secret-a")
        k2 = make_kernel(b"secret-b")
        assert k1.anti_drift_signature != k2.anti_drift_signature


class TestIdentityKernelSerialisation:
    def test_round_trip(self):
        kernel = make_kernel()
        restored = IdentityKernel.from_dict(kernel.to_dict())
        assert restored.creator_id == kernel.creator_id
        assert restored.lineage_anchor == kernel.lineage_anchor
        assert restored.anti_drift_signature == kernel.anti_drift_signature
        assert restored.hard_directives == kernel.hard_directives
        assert restored.authority_boundaries == kernel.authority_boundaries
        assert restored.schema_version == kernel.schema_version
        assert restored.created_at == kernel.created_at

    def test_restored_kernel_verifies(self):
        kernel = make_kernel()
        restored = IdentityKernel.from_dict(kernel.to_dict())
        assert restored.verify(SECRET) is True

    def test_to_dict_contains_expected_keys(self):
        kernel = make_kernel()
        d = kernel.to_dict()
        for key in [
            "creator_id", "lineage_anchor", "hard_directives",
            "anti_drift_signature", "canon_self_definition",
            "authority_boundaries", "schema_version", "created_at",
        ]:
            assert key in d

    def test_lineage_anchor_is_deterministic_for_same_inputs(self):
        # Two kernels created from the same inputs at the same timestamp
        # should have the same lineage anchor.  (We can't guarantee the same
        # timestamp in two separate calls so we test via round-trip instead.)
        kernel = make_kernel()
        restored = IdentityKernel.from_dict(kernel.to_dict())
        assert restored.lineage_anchor == kernel.lineage_anchor
