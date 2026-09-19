from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceObjective:
    id: str
    title: str
    next_action: str
    stage: str
    value: float
    readiness: float
    evidence: float
    reversibility: float
    leverage: float
    cost: float
    delay: float
    dependency: float
    revenue_potential: float
    deployment_gap: float
    blocker: Optional[str] = None
    evidence_ref: Optional[str] = None


def _run_gh(args: list[str]) -> Any:
    try:
        proc = subprocess.run(
            ["gh", *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise SourceError("GitHub CLI 'gh' is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise SourceError("GitHub CLI request timed out") from exc

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        raise SourceError(f"gh failed ({proc.returncode}): {msg}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SourceError("gh returned invalid JSON") from exc


def github_pr_objectives(repositories: Iterable[str]) -> list[SourceObjective]:
    out: list[SourceObjective] = []
    for repo in repositories:
        prs = _run_gh([
            "api",
            f"repos/{repo}/pulls?state=open&per_page=100",
            "--paginate",
            "--slurp",
        ])
        flat = [pr for page in prs for pr in page] if prs and isinstance(prs[0], list) else prs
        for pr in flat:
            number = int(pr["number"])
            draft = bool(pr.get("draft"))
            mergeable = pr.get("mergeable")
            title = str(pr.get("title") or f"PR #{number}")
            body = str(pr.get("body") or "")
            labels = [str(x.get("name", "")).lower() for x in pr.get("labels", [])]
            lower = (title + "\n" + body + "\n" + " ".join(labels)).lower()

            revenue = 5.0 if any(k in lower for k in ("revenue", "payment", "customer", "checkout", "billing")) else 1.0
            deploy_gap = 5.0 if any(k in lower for k in ("deploy", "physical", "release", "apk", "production")) else 2.0
            stage = "DEPLOY" if deploy_gap >= 5 else ("SELL" if revenue >= 5 else "VERIFY")
            readiness = 4.5 if mergeable is True and not draft else (3.5 if mergeable is True else 2.5)
            evidence = 4.0 if pr.get("head", {}).get("sha") else 2.0

            blocker = None
            next_action = f"Review and close PR #{number} in {repo}"
            if draft:
                blocker = "PR is draft; satisfy its documented approval/verification gates"
                next_action = f"Satisfy draft gates for {repo} PR #{number}"
            elif mergeable is False:
                blocker = "PR is not mergeable; resolve conflicts or branch divergence"
                next_action = f"Resolve mergeability for {repo} PR #{number}"

            out.append(SourceObjective(
                id=f"github:{repo}:pr:{number}",
                title=f"{repo} PR #{number}: {title}",
                next_action=next_action,
                stage=stage,
                value=4.0,
                readiness=readiness,
                evidence=evidence,
                reversibility=4.0,
                leverage=4.0,
                cost=2.0 if mergeable is True else 3.0,
                delay=2.0,
                dependency=2.0,
                revenue_potential=revenue,
                deployment_gap=deploy_gap,
                blocker=blocker,
                evidence_ref=pr.get("html_url"),
            ))
    return out


def intent_graph_objectives(path: str | Path) -> list[SourceObjective]:
    p = Path(path)
    if not p.exists():
        raise SourceError(f"intent graph snapshot not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    nodes = raw.get("nodes", [])
    edges = raw.get("edges", [])
    blocked_by: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("edge_type") == "blocked_by":
            blocked_by.setdefault(str(edge["source_id"]), []).append(str(edge["target_id"]))

    out: list[SourceObjective] = []
    for node in nodes:
        status = str(node.get("status", "")).lower()
        if status not in {"active", "dormant"}:
            continue
        metadata = dict(node.get("metadata") or {})
        nid = str(node["id"])
        blockers = blocked_by.get(nid, [])
        stage = str(metadata.get("stage", "BUILD")).upper()
        if stage not in {"DISCOVERY","BUILD","VERIFY","DEPLOY","SELL","OBSERVE","SCALE"}:
            stage = "BUILD"

        def score(name: str, default: float) -> float:
            try:
                return max(0.0, min(5.0, float(metadata.get(name, default))))
            except (TypeError, ValueError):
                return default

        next_action = str(metadata.get("next_action") or node.get("description") or "Define next externally verifiable action")
        out.append(SourceObjective(
            id=f"intent:{nid}",
            title=str(node.get("title") or nid),
            next_action=next_action,
            stage=stage,
            value=score("value", 3.5),
            readiness=score("readiness", 3.0),
            evidence=score("evidence", 2.5),
            reversibility=score("reversibility", 3.0),
            leverage=score("leverage", 3.5),
            cost=max(0.1, score("cost", 3.0)),
            delay=max(0.1, score("delay", 3.0)),
            dependency=max(0.1, score("dependency", 3.0)),
            revenue_potential=score("revenue_potential", 0.0),
            deployment_gap=score("deployment_gap", 0.0),
            blocker=(f"Blocked by intent ids: {', '.join(blockers)}" if blockers else None),
            evidence_ref=f"intent:{nid}",
        ))
    return out
