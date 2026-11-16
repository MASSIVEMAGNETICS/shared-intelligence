import json
from datetime import datetime, timedelta, timezone

import pytest

import bando_driver
from bando_driver import BandoDriver, CapacityError, DriverError, Objective, ValidationError
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


@pytest.mark.parametrize(
    "field",
    [
        "value", "readiness", "evidence", "reversibility", "leverage",
        "cost", "delay", "dependency", "revenue_potential", "deployment_gap",
    ],
)
def test_boolean_numeric_fields_are_rejected(field):
    with pytest.raises(ValidationError, match=f"{field} must be finite"):
        make_obj("bad", **{field: True}).validate()


@pytest.mark.parametrize("max_active", [True, False, 0, -1, 1.5, "3"])
def test_constructor_rejects_invalid_max_active(max_active, tmp_path):
    with pytest.raises(ValidationError, match="max_active"):
        BandoDriver(tmp_path / "registry.json", max_active=max_active)


@pytest.mark.parametrize("schema_version", [True, 1.0, "1"])
def test_registry_schema_version_requires_json_integer(schema_version, tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": schema_version, "max_active": 3, "objectives": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="schema_version"):
        BandoDriver(path)


@pytest.mark.parametrize("max_active", [True, False, 0, -1, 3.0, "3"])
def test_registry_max_active_requires_positive_json_integer(max_active, tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_active": max_active, "objectives": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="max_active"):
        BandoDriver(path)


def test_registry_top_level_must_be_json_object(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError, match="JSON object"):
        BandoDriver(path)


def test_registry_objectives_must_be_json_array(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_active": 3, "objectives": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="JSON array"):
        BandoDriver(path)


def test_registry_objective_entries_must_be_json_objects(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_active": 3, "objectives": ["not-an-object"]}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match=r"objectives\[0\]"):
        BandoDriver(path)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", 7, "id must be a non-empty string"),
        ("title", None, "title must be a non-empty string"),
        ("next_action", [], "next_action must be a string"),
        ("created_at", 123, "created_at must be a non-empty ISO-8601 string"),
        ("updated_at", "", "updated_at must be a non-empty ISO-8601 string"),
        ("blocker", 7, "blocker must be a non-empty string or null"),
        ("evidence_ref", {}, "evidence_ref must be a non-empty string or null"),
        ("kill_condition", False, "kill_condition must be a non-empty string or null"),
        ("novelty_quarantine_until", 123, "novelty_quarantine_until must be a non-empty ISO-8601 string or null"),
    ],
)
def test_objective_rejects_invalid_text_and_timestamp_fields(field, value, message):
    with pytest.raises(ValidationError, match=message):
        make_obj("bad", **{field: value}).validate()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state", "RUNNING"),
        ("state", []),
        ("stage", "RELEASE"),
        ("stage", None),
    ],
)
def test_objective_rejects_unknown_state_and_stage_values(field, value):
    with pytest.raises(ValidationError, match=field):
        make_obj("bad", **{field: value}).validate()


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_objective_timestamps_must_be_parseable_iso8601(field):
    with pytest.raises(ValidationError, match=f"{field} must be a valid ISO-8601 timestamp"):
        make_obj("bad", **{field: "not-a-timestamp"}).validate()


def test_objective_quarantine_timestamp_must_be_parseable_iso8601():
    objective = make_obj("bad", novelty_quarantine_until="not-a-timestamp")
    with pytest.raises(ValidationError, match="novelty_quarantine_until"):
        objective.quarantined()


def test_terminal_objective_requires_evidence_reference():
    with pytest.raises(ValidationError, match="DONE objective requires evidence_ref"):
        make_obj("done", state="DONE").validate()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 7),
        ("state", "RUNNING"),
        ("stage", "RELEASE"),
        ("novelty_quarantine_until", "not-a-timestamp"),
    ],
)
def test_registry_rejects_malformed_objective_before_loading(tmp_path, field, value):
    record = make_obj("candidate").__dict__.copy()
    record[field] = value
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_active": 3, "objectives": [record]}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        BandoDriver(path)


def test_registry_rejects_terminal_objective_without_evidence_reference(tmp_path):
    record = make_obj("done", state="DONE").__dict__.copy()
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_active": 3, "objectives": [record]}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="DONE objective requires evidence_ref"):
        BandoDriver(path)

@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_registry_requires_persisted_timestamps(field, tmp_path):
    record = make_obj("candidate").__dict__.copy()
    record.pop(field)
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_active": 3, "objectives": [record]}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="missing persisted timestamps") as exc:
        BandoDriver(path)
    assert field in str(exc.value)


def test_sync_fails_closed_when_configured_intent_graph_snapshot_is_missing(monkeypatch, tmp_path):
    config_path = tmp_path / "stack.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repositories": ["MASSIVEMAGNETICS/example"],
                "intent_graph_snapshot": "missing/intent_graph.json",
                "max_active": 3,
                "policy": {"activate_top": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        bando_driver,
        "github_pr_objectives",
        lambda repos: pytest.fail("GitHub sources must not be read after a missing configured snapshot"),
    )
    registry = tmp_path / "registry.json"

    with pytest.raises(
        bando_driver.DriverError,
        match="configured intent graph snapshot does not exist or is not a file",
    ):
        bando_driver.main(
            ["--registry", str(registry), "sync", "--config", str(config_path), "--no-activate"]
        )

    assert not registry.exists()


def test_explicit_intent_graph_overrides_missing_configured_snapshot(monkeypatch, tmp_path):
    config_path = tmp_path / "stack.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repositories": ["MASSIVEMAGNETICS/example"],
                "intent_graph_snapshot": "missing/intent_graph.json",
                "max_active": 3,
                "policy": {"activate_top": True},
            }
        ),
        encoding="utf-8",
    )
    explicit_snapshot = tmp_path / "explicit-intent.json"
    explicit_snapshot.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bando_driver, "github_pr_objectives", lambda repos: [])
    observed_paths = []
    monkeypatch.setattr(
        bando_driver,
        "intent_graph_objectives",
        lambda path: (observed_paths.append(path) or [source_obj("intent:explicit-override")]),
    )
    registry = tmp_path / "registry.json"

    result = bando_driver.main(
        [
            "--registry", str(registry), "sync", "--config", str(config_path),
            "--intent-graph", str(explicit_snapshot), "--no-activate",
        ]
    )

    assert result == 0
    assert observed_paths == [str(explicit_snapshot)]
    saved = json.loads(registry.read_text(encoding="utf-8"))
    assert [item["id"] for item in saved["objectives"]] == ["intent:explicit-override"]
    assert saved["objectives"][0]["state"] == "QUEUED"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"schema_version": True}, "schema_version"),
        ({"repositories": "MASSIVEMAGNETICS/example"}, "repositories must be a JSON array"),
        ({"repositories": [True]}, r"repositories\[0\]"),
        ({"repositories": ["MASSIVEMAGNETICS/example/extra"]}, "owner/name"),
        ({"max_active": True}, "max_active"),
        ({"max_active": 0}, "max_active"),
        ({"max_active": 1.5}, "max_active"),
        ({"policy": []}, "policy must be a JSON object"),
        ({"policy": {"activate_top": "false"}}, "policy.activate_top"),
        ({"intent_graph_snapshot": 7}, "intent_graph_snapshot"),
        ({"intent_graph_snapshot": ""}, "intent_graph_snapshot"),
    ],
)
def test_sync_rejects_malformed_stack_config_before_github_reads(
    monkeypatch, tmp_path, override, message
):
    config = {
        "schema_version": 1,
        "repositories": ["MASSIVEMAGNETICS/example"],
        "max_active": 3,
        "policy": {"activate_top": False},
    }
    config.update(override)
    config_path = tmp_path / "stack.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        bando_driver,
        "github_pr_objectives",
        lambda repos: pytest.fail("GitHub sources must not be read for an invalid stack config"),
    )
    registry = tmp_path / "registry.json"

    with pytest.raises(DriverError, match=message):
        bando_driver.main(
            ["--registry", str(registry), "sync", "--config", str(config_path), "--no-activate"]
        )

    assert not registry.exists()


def test_sync_rejects_non_object_stack_config_before_github_reads(monkeypatch, tmp_path):
    config_path = tmp_path / "stack.json"
    config_path.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        bando_driver,
        "github_pr_objectives",
        lambda repos: pytest.fail("GitHub sources must not be read for a non-object stack config"),
    )

    with pytest.raises(DriverError, match="stack config must be a JSON object"):
        bando_driver.main(
            ["--registry", str(tmp_path / "registry.json"), "sync", "--config", str(config_path)]
        )


def test_sync_wraps_malformed_stack_config_json(monkeypatch, tmp_path):
    config_path = tmp_path / "stack.json"
    config_path.write_text("{", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(DriverError, match="unable to read stack config"):
        bando_driver.main(
            ["--registry", str(tmp_path / "registry.json"), "sync", "--config", str(config_path)]
        )


def test_sync_accepts_valid_stack_config_and_respects_boolean_activation(monkeypatch, tmp_path):
    config_path = tmp_path / "stack.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repositories": ["MASSIVEMAGNETICS/example"],
                "max_active": 2,
                "policy": {"activate_top": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        bando_driver,
        "github_pr_objectives",
        lambda repos: [source_obj("github:MASSIVEMAGNETICS/example:pr:1")],
    )
    registry = tmp_path / "registry.json"

    result = bando_driver.main(
        ["--registry", str(registry), "sync", "--config", str(config_path)]
    )

    assert result == 0
    saved = json.loads(registry.read_text(encoding="utf-8"))
    assert saved["max_active"] == 2
    assert saved["objectives"][0]["state"] == "QUEUED"

@pytest.mark.parametrize(
    ("stage", "stage_boost"),
    [
        ("DISCOVERY", 0.70),
        ("BUILD", 0.90),
        ("VERIFY", 1.05),
        ("DEPLOY", 1.20),
        ("SELL", 1.35),
        ("OBSERVE", 1.10),
        ("SCALE", 1.15),
    ],
)
def test_score_formula_is_preserved_for_each_stage(stage, stage_boost):
    objective = make_obj(
        f"score-{stage.lower()}",
        stage=stage,
        value=2.0,
        readiness=3.0,
        evidence=4.0,
        reversibility=5.0,
        leverage=2.0,
        cost=2.0,
        delay=3.0,
        dependency=4.0,
        revenue_potential=5.0,
        deployment_gap=4.0,
    )
    base = (2.0 * 3.0 * 4.0 * 5.0 * 2.0) / (2.0 * 3.0 * 4.0)
    expected = base * 1.9 * 1.48 * stage_boost
    assert objective.score() == pytest.approx(expected)


def test_score_formula_preserves_blocked_penalty():
    objective = make_obj(
        "score-blocked",
        state="BLOCKED",
        blocker="independent review required",
        stage="VERIFY",
        value=2.0,
        readiness=3.0,
        evidence=4.0,
        reversibility=5.0,
        leverage=2.0,
        cost=2.0,
        delay=3.0,
        dependency=4.0,
        revenue_potential=5.0,
        deployment_gap=4.0,
    )
    base = (2.0 * 3.0 * 4.0 * 5.0 * 2.0) / (2.0 * 3.0 * 4.0)
    expected = base * 1.9 * 1.48 * 1.05 * 0.15
    assert objective.score() == pytest.approx(expected)


def test_score_formula_keeps_terminal_objectives_at_zero():
    objective = make_obj(
        "score-done",
        state="DONE",
        evidence_ref="sha256:verified-test-evidence",
        stage="SELL",
        value=5.0,
        readiness=5.0,
        evidence=5.0,
        reversibility=5.0,
        leverage=5.0,
        cost=1.0,
        delay=1.0,
        dependency=1.0,
        revenue_potential=5.0,
        deployment_gap=5.0,
    )
    assert objective.score() == 0.0
