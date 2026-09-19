import json
from datetime import datetime, timedelta, timezone

import pytest

from bando_driver import (
    BandoDriver,
    CapacityError,
    Objective,
    ValidationError,
)


def make_obj(i: str, **kw):
    base = dict(
        id=i,
        title=f"Objective {i}",
        next_action="Do the next externally verifiable action",
        value=3,
        readiness=3,
        evidence=3,
        reversibility=3,
        leverage=3,
        cost=3,
        delay=3,
        dependency=3,
    )
    base.update(kw)
    return Objective(**base)


def test_wip_limit_blocks_fourth_active(tmp_path):
    path = tmp_path / "registry.json"
    d = BandoDriver(path, max_active=3)
    for i in ("a", "b", "c"):
        d.add(make_obj(i), activate=True)
    with pytest.raises(CapacityError):
        d.add(make_obj("d"), activate=True)


def test_terminal_state_requires_evidence(tmp_path):
    d = BandoDriver(tmp_path / "r.json")
    d.add(make_obj("a"), activate=True)
    with pytest.raises(ValidationError):
        d.set_state("a", "DONE")
    d.set_state("a", "DONE", evidence_ref="sha256:abc")
    assert d.require("a").state == "DONE"
    assert d.require("a").next_action == ""


def test_blocked_requires_blocker(tmp_path):
    d = BandoDriver(tmp_path / "r.json")
    d.add(make_obj("a"), activate=True)
    with pytest.raises(ValidationError):
        d.set_state("a", "BLOCKED")
    d.set_state("a", "BLOCKED", blocker="waiting on physical device")
    assert d.require("a").blocker == "waiting on physical device"


def test_sell_stage_and_revenue_can_outrank_build(tmp_path):
    d = BandoDriver(tmp_path / "r.json")
    d.add(make_obj("build", stage="BUILD"), activate=True)
    d.add(make_obj("sell", stage="SELL", revenue_potential=5), activate=True)
    assert d.next().id == "sell"


def test_deployment_gap_boosts_closure_work(tmp_path):
    d = BandoDriver(tmp_path / "r.json")
    d.add(make_obj("ordinary", stage="BUILD"), activate=True)
    d.add(make_obj("deploy", stage="DEPLOY", deployment_gap=5), activate=True)
    assert d.next().id == "deploy"


def test_novelty_quarantine_excludes_new_idea(tmp_path):
    d = BandoDriver(tmp_path / "r.json")
    d.add(make_obj("active", stage="VERIFY"), activate=True)
    future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    d.add(make_obj(
        "shiny",
        value=5,
        readiness=5,
        evidence=5,
        leverage=5,
        novelty_quarantine_until=future,
    ))
    assert d.next().id == "active"


def test_queued_option_needs_20_percent_advantage_and_capacity(tmp_path):
    d = BandoDriver(tmp_path / "r.json", max_active=3)
    d.add(make_obj("active", stage="BUILD"), activate=True)
    d.add(make_obj(
        "queued",
        stage="SELL",
        revenue_potential=5,
        value=5,
        readiness=5,
        evidence=5,
        reversibility=5,
        leverage=5,
        cost=1,
        delay=1,
        dependency=1,
    ))
    assert d.next().id == "queued"


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "registry.json"
    d = BandoDriver(path)
    d.add(make_obj("a"), activate=True)
    d.update("a", evidence_ref="run:123")
    d2 = BandoDriver(path)
    assert d2.require("a").evidence_ref == "run:123"
    assert d2.status()["active_count"] == 1


def test_registry_is_valid_json(tmp_path):
    path = tmp_path / "registry.json"
    d = BandoDriver(path)
    d.add(make_obj("a"))
    raw = json.loads(path.read_text())
    assert raw["schema_version"] == 1
    assert raw["objectives"][0]["id"] == "a"


def test_invalid_numeric_bounds_rejected():
    with pytest.raises(ValidationError):
        make_obj("bad", value=6).validate()
