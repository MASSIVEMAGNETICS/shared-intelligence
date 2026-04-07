"""Tests for LegacyPersistenceLayer."""

import json
import tempfile
from pathlib import Path

import pytest
from victor.persistence.layer import (
    Checkpoint,
    CorruptionError,
    LegacyPersistenceLayer,
    MigrationError,
)

SECRET = b"persistence-secret-key"


def make_layer(tmp_path: Path | None = None) -> LegacyPersistenceLayer:
    return LegacyPersistenceLayer(secret_key=SECRET, storage_path=tmp_path)


def make_payload(label: str = "test") -> dict:
    return {"label": label, "data": {"x": 1, "y": 2}}


class TestCheckpoint:
    def test_round_trip(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload("round-trip"))
        restored = Checkpoint.from_dict(cp.to_dict())
        assert restored.id == cp.id
        assert restored.signature == cp.signature
        assert restored.payload == cp.payload


class TestLegacyPersistenceLayer:
    def test_checkpoint_creates_entry(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload())
        assert cp.id
        assert len(layer.lineage()) == 1

    def test_lineage_chain(self):
        layer = make_layer()
        cp1 = layer.checkpoint(make_payload("first"))
        cp2 = layer.checkpoint(make_payload("second"))
        assert cp2.previous_checkpoint_id == cp1.id
        assert cp1.previous_checkpoint_id is None

    def test_verify_passes_for_valid(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload())
        assert layer.verify(cp) is True

    def test_verify_fails_for_tampered_payload(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload())
        # Directly mutate payload to simulate corruption
        cp.payload["tampered"] = True
        assert layer.verify(cp) is False

    def test_assert_valid_raises_on_corruption(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload())
        cp.payload["hacked"] = True
        with pytest.raises(CorruptionError):
            layer.assert_valid(cp)

    def test_rehydrate_returns_latest(self):
        layer = make_layer()
        layer.checkpoint(make_payload("first"))
        layer.checkpoint(make_payload("latest"))
        payload = layer.rehydrate()
        assert payload["label"] == "latest"

    def test_rehydrate_by_id(self):
        layer = make_layer()
        cp1 = layer.checkpoint(make_payload("first"))
        layer.checkpoint(make_payload("second"))
        payload = layer.rehydrate(cp1.id)
        assert payload["label"] == "first"

    def test_rehydrate_unknown_id_raises(self):
        layer = make_layer()
        with pytest.raises(KeyError):
            layer.rehydrate("nonexistent-id")

    def test_rehydrate_none_when_empty(self):
        layer = make_layer()
        assert layer.rehydrate() is None

    def test_latest_returns_none_when_empty(self):
        layer = make_layer()
        assert layer.latest() is None

    def test_migration_same_version_is_noop(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload())
        migrated = layer.migrate(cp)
        assert migrated.id == cp.id  # no new checkpoint created

    def test_migration_unsupported_version_raises(self):
        layer = make_layer()
        cp = layer.checkpoint(make_payload())
        # Force an unsupported source version
        old = Checkpoint(
            id=cp.id,
            schema_version="0.0.1",
            created_at=cp.created_at,
            payload=cp.payload,
            signature=cp.signature,
            previous_checkpoint_id=cp.previous_checkpoint_id,
            metadata=cp.metadata,
        )
        with pytest.raises(MigrationError):
            layer.migrate(old)

    def test_summarise_lineage(self):
        layer = make_layer()
        layer.checkpoint(make_payload("a"))
        layer.checkpoint(make_payload("b"))
        summary = layer.summarise_lineage()
        assert summary["total_checkpoints"] == 2
        assert len(summary["ids"]) == 2

    def test_disk_persistence(self, tmp_path: Path):
        layer = LegacyPersistenceLayer(secret_key=SECRET, storage_path=tmp_path)
        cp = layer.checkpoint(make_payload("disk-test"))
        # File should exist
        filepath = tmp_path / f"{cp.id}.json"
        assert filepath.exists()
        # Load from disk
        loaded = layer.load_from_disk(cp.id)
        assert loaded.id == cp.id
        assert loaded.payload["label"] == "disk-test"

    def test_disk_load_detects_corruption(self, tmp_path: Path):
        layer = LegacyPersistenceLayer(secret_key=SECRET, storage_path=tmp_path)
        cp = layer.checkpoint(make_payload("original"))
        filepath = tmp_path / f"{cp.id}.json"
        # Corrupt the file
        data = json.loads(filepath.read_text())
        data["payload"]["label"] = "corrupted"
        filepath.write_text(json.dumps(data))
        with pytest.raises(CorruptionError):
            layer.load_from_disk(cp.id)
