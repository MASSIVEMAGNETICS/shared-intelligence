import json
from datetime import datetime, timedelta, timezone

import pytest

import bando_driver
from bando_driver import BandoDriver, CapacityError, Objective, ValidationError
from bando_sources import SourceObjective


def make_obj(i: str, **kw):
    base = dict(id=i, title=f"Objective {i}", next_action="Do the next externally verifiable action", value=3, readiness=3, evidence=3, reversibility=3, leverage=3, cost=3, delay=3, dependency=3)
    base.update(kw)
    return Objective(**base)


def source_obj(i: str, blocker=None):
    return SourceObjective(id=i, title=i, next_action="verify upstream authority", stage="VERIFY", value=5, readiness=5, evidence=5, reversibility=5, leverage=5, cost=1, delay=1, dependency=1, revenue_potential=0, deployment_gap=5, blocker=blocker)


def test_wip_limit_blocks_fourth_active(tmp_path):
    path=tmp_path/"registry.json"; d=BandoDriver(path,max_active=3)
    for i in ("a","b","c"): d.add(make_obj(i),activate=True)
    with pytest.raises(CapacityError): d.add(make_obj("d"),activate=True)


def test_terminal_state_requires_evidence(tmp_path):
    d=BandoDriver(tmp_path/"r.json"); d.add(make_obj("a"),activate=True)
    with pytest.raises(ValidationError): d.set_state("a","DONE")
    d.set_state("a","DONE",evidence_ref="sha256:abc"); assert d.require("a").next_action==""


def test_blocked_requires_blocker(tmp_path):
    d=BandoDriver(tmp_path/"r.json"); d.add(make_obj("a"),activate=True)
    with pytest.raises(ValidationError): d.set_state("a","BLOCKED")
    d.set_state("a","BLOCKED",blocker="waiting on physical device"); assert d.require("a").blocker


def test_sell_stage_and_revenue_can_outrank_build(tmp_path):
    d=BandoDriver(tmp_path/"r.json"); d.add(make_obj("build",stage="BUILD"),activate=True); d.add(make_obj("sell",stage="SELL",revenue_potential=5),activate=True); assert d.next().id=="sell"


def test_deployment_gap_boosts_closure_work(tmp_path):
    d=BandoDriver(tmp_path/"r.json"); d.add(make_obj("ordinary",stage="BUILD"),activate=True); d.add(make_obj("deploy",stage="DEPLOY",deployment_gap=5),activate=True); assert d.next().id=="deploy"


def test_novelty_quarantine_excludes_new_idea(tmp_path):
    d=BandoDriver(tmp_path/"r.json"); d.add(make_obj("active",stage="VERIFY"),activate=True); future=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(); d.add(make_obj("shiny",value=5,readiness=5,evidence=5,leverage=5,novelty_quarantine_until=future)); assert d.next().id=="active"


def test_queued_option_needs_20_percent_advantage_and_capacity(tmp_path):
    d=BandoDriver(tmp_path/"r.json",max_active=3); d.add(make_obj("active",stage="BUILD"),activate=True); d.add(make_obj("queued",stage="SELL",revenue_potential=5,value=5,readiness=5,evidence=5,reversibility=5,leverage=5,cost=1,delay=1,dependency=1)); assert d.next().id=="queued"


def test_persistence_roundtrip(tmp_path):
    path=tmp_path/"registry.json"; d=BandoDriver(path); d.add(make_obj("a"),activate=True); d.update("a",evidence_ref="run:123"); d2=BandoDriver(path); assert d2.require("a").evidence_ref=="run:123" and d2.status()["active_count"]==1


def test_registry_is_valid_json(tmp_path):
    path=tmp_path/"registry.json"; d=BandoDriver(path); d.add(make_obj("a")); raw=json.loads(path.read_text()); assert raw["schema_version"]==1 and raw["objectives"][0]["id"]=="a"


def test_invalid_numeric_bounds_rejected():
    with pytest.raises(ValidationError): make_obj("bad",value=6).validate()


def test_sync_revokes_active_when_source_becomes_blocked(tmp_path):
    d=BandoDriver(tmp_path/"r.json",max_active=3); source=source_obj("github:MASSIVEMAGNETICS/victorOS:pr:17"); d.sync_sources([source]); assert d.require(source.id).state=="ACTIVE"
    blocked=source_obj(source.id,blocker="PR is draft; approval required"); d.sync_sources([blocked]); obj=d.require(source.id); assert obj.state=="BLOCKED" and obj.id not in [x.id for x in d.active()]


def test_sync_preserves_active_when_source_remains_unblocked(tmp_path):
    d=BandoDriver(tmp_path/"r.json",max_active=3); source=source_obj("intent:ship-victor"); d.sync_sources([source]); assert d.require(source.id).state=="ACTIVE"; d.sync_sources([source]); assert d.require(source.id).state=="ACTIVE"


def test_authoritative_sync_revokes_active_source_that_disappears(tmp_path):
    d=BandoDriver(tmp_path/"r.json",max_active=3)
    oid="github:MASSIVEMAGNETICS/victorOS:pr:17"; source=source_obj(oid)
    d.sync_sources([source],authoritative_prefixes=["github:MASSIVEMAGNETICS/victorOS:pr:"])
    assert d.require(oid).state=="ACTIVE"
    result=d.sync_sources([],authoritative_prefixes=["github:MASSIVEMAGNETICS/victorOS:pr:"])
    assert d.require(oid).state=="BLOCKED"
    assert oid in result["revoked_absent"]
    assert "absent" in d.require(oid).blocker


def test_partial_sync_does_not_revoke_unseen_objective(tmp_path):
    d=BandoDriver(tmp_path/"r.json",max_active=3)
    oid="github:MASSIVEMAGNETICS/victorOS:pr:17"; source=source_obj(oid)
    d.sync_sources([source]); assert d.require(oid).state=="ACTIVE"
    d.sync_sources([])
    assert d.require(oid).state=="ACTIVE"


def test_authoritative_scope_does_not_revoke_other_repo(tmp_path):
    d=BandoDriver(tmp_path/"r.json",max_active=3)
    a=source_obj("github:MASSIVEMAGNETICS/victorOS:pr:17"); b=source_obj("github:MASSIVEMAGNETICS/victor_empire:pr:8")
    d.sync_sources([a,b]); assert d.require(b.id).state=="ACTIVE"
    d.sync_sources([],authoritative_prefixes=["github:MASSIVEMAGNETICS/victorOS:pr:"])
    assert d.require(a.id).state=="BLOCKED"
    assert d.require(b.id)==d.require(b.id) and d.require(b.id).state=="ACTIVE"


def test_stale_writer_cannot_silently_erase_concurrent_registry_update(tmp_path):
    path=tmp_path/"registry.json"
    seed=BandoDriver(path); seed.add(make_obj("seed"))

    first=BandoDriver(path)
    stale=BandoDriver(path)
    first.add(make_obj("first"))
    stale.add(make_obj("stale"))

    final=BandoDriver(path)
    assert set(final.objectives) == {"seed", "first", "stale"}


def test_mutation_fails_closed_without_platform_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(bando_driver, "fcntl", None)
    monkeypatch.setattr(bando_driver, "msvcrt", None)
    path=tmp_path/"registry.json"

    with pytest.raises(bando_driver.DriverError, match="no supported inter-process registry lock"):
        BandoDriver(path).add(make_obj("unsafe"))

    assert not path.exists()


def test_failed_mutation_releases_lock_and_preserves_latest_registry(tmp_path):
    path=tmp_path/"registry.json"
    first=BandoDriver(path); first.add(make_obj("first"))

    with pytest.raises(ValidationError):
        first.add(make_obj("invalid", cost=0))

    BandoDriver(path).add(make_obj("second"))
    assert set(BandoDriver(path).objectives) == {"first", "second"}
