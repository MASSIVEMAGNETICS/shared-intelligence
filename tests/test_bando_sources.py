import json
from pathlib import Path

import pytest

import bando_sources
from bando_driver import BandoDriver
from bando_sources import SourceObjective, intent_graph_objectives


def test_intent_graph_source_import(tmp_path):
    graph = {
        "nodes": [
            {
                "id": "mission-1",
                "node_type": "strategic_mission",
                "title": "Ship Victor",
                "description": "Install on target phone",
                "status": "active",
                "created_at": "2026-09-19T00:00:00+00:00",
                "metadata": {
                    "stage": "DEPLOY",
                    "value": 5,
                    "readiness": 4,
                    "evidence": 4,
                    "leverage": 5,
                    "deployment_gap": 5,
                    "next_action": "Install exact APK on physical target",
                },
            }
        ],
        "edges": [],
    }
    p = tmp_path / "intent.json"
    p.write_text(json.dumps(graph))
    rows = intent_graph_objectives(p)
    assert len(rows) == 1
    assert rows[0].id == "intent:mission-1"
    assert rows[0].stage == "DEPLOY"
    assert rows[0].deployment_gap == 5


def test_sync_sources_activates_top_three(tmp_path):
    d = BandoDriver(tmp_path / "r.json", max_active=3)
    rows = [
        SourceObjective(
            id=f"x:{i}",
            title=f"X {i}",
            next_action="close it",
            stage="SELL" if i == 0 else "BUILD",
            value=5 if i == 0 else 3,
            readiness=4,
            evidence=4,
            reversibility=4,
            leverage=4,
            cost=2,
            delay=2,
            dependency=2,
            revenue_potential=5 if i == 0 else 0,
            deployment_gap=0,
        )
        for i in range(5)
    ]
    result = d.sync_sources(rows)
    assert len(d.active()) == 3
    assert result["decision"]["objective_id"] == "x:0"


def test_sync_blocked_source_not_auto_activated(tmp_path):
    d = BandoDriver(tmp_path / "r.json", max_active=3)
    row = SourceObjective(
        id="x:block",
        title="Blocked",
        next_action="resolve gate",
        stage="VERIFY",
        value=5,
        readiness=5,
        evidence=5,
        reversibility=5,
        leverage=5,
        cost=1,
        delay=1,
        dependency=1,
        revenue_potential=5,
        deployment_gap=5,
        blocker="human approval required",
    )
    d.sync_sources([row])
    assert d.require("x:block").state == "BLOCKED"


def test_github_pr_source_uses_gh_json(monkeypatch):
    payload = [[{
        "number": 8,
        "draft": True,
        "mergeable": True,
        "title": "Add revenue deployment",
        "body": "customer payment and deploy",
        "labels": [],
        "head": {"sha": "abc"},
        "html_url": "https://example/pr/8",
    }]]

    monkeypatch.setattr(bando_sources, "_run_gh", lambda args: payload)
    rows = bando_sources.github_pr_objectives(["MASSIVEMAGNETICS/victor_empire"])
    assert rows[0].id.endswith(":pr:8")
    assert rows[0].stage == "DEPLOY"
    assert rows[0].revenue_potential == 5
    assert rows[0].blocker is not None


def test_next_falls_back_to_highest_value_blocker(tmp_path):
    d = BandoDriver(tmp_path / "r.json", max_active=3)
    low = SourceObjective(
        id="x:low", title="Low blocker", next_action="resolve low", stage="VERIFY",
        value=2, readiness=2, evidence=2, reversibility=3, leverage=2,
        cost=3, delay=3, dependency=3, revenue_potential=0, deployment_gap=0,
        blocker="low-value gate",
    )
    high = SourceObjective(
        id="x:high", title="High blocker", next_action="resolve high", stage="DEPLOY",
        value=5, readiness=5, evidence=5, reversibility=5, leverage=5,
        cost=1, delay=1, dependency=1, revenue_potential=5, deployment_gap=5,
        blocker="high-value gate",
    )
    d.sync_sources([low, high])
    decision = d.decision()
    assert decision["objective_id"] == "x:high"
    assert decision["state"] == "BLOCKED"
    assert decision["reason"].startswith("resolve blocker:")
