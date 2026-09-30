from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
from typing import Any, Iterable, Mapping


class OperatorError(RuntimeError):
    pass


class WIPLimitExceeded(OperatorError):
    pass


class HumanStopActive(OperatorError):
    pass


class AuthorityDenied(OperatorError):
    pass


class ApprovalMismatch(OperatorError):
    pass


@dataclasses.dataclass(frozen=True)
class CapabilityLease:
    lease_id: str
    capabilities: frozenset[str]
    resources: frozenset[str]
    issued_at: float
    expires_at: float
    revoked: bool = False
    spend_limit: float | None = None

    def is_active(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return (not self.revoked) and self.issued_at <= now <= self.expires_at

    def allows(self, capability: str, resource: str, now: float | None = None) -> bool:
        return (
            self.is_active(now)
            and capability in self.capabilities
            and resource in self.resources
        )


@dataclasses.dataclass(frozen=True)
class HumanApproval:
    approval_id: str
    issued_by: str
    repository: str
    pr_number: int
    exact_sha: str
    issued_at: float
    expires_at: float | None = None
    revoked: bool = False

    def is_active(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self.revoked:
            return False
        if self.expires_at is not None and now > self.expires_at:
            return False
        return self.issued_at <= now

    def authorizes(
        self,
        repository: str,
        pr_number: int,
        exact_sha: str,
        now: float | None = None,
    ) -> bool:
        return (
            self.is_active(now)
            and self.repository == repository
            and self.pr_number == pr_number
            and hmac.compare_digest(self.exact_sha, exact_sha)
        )


@dataclasses.dataclass
class Task:
    task_id: str
    objective_id: str
    title: str
    authority_class: int
    status: str = "READY"
    required_capability: str | None = None
    resource: str | None = None
    budget: float = 0.0
    terminal_condition: str = ""
    acceptance_test: str = ""


@dataclasses.dataclass(frozen=True)
class DecisionCandidate:
    candidate_id: str
    task_id: str
    expected_value: float
    confidence: float
    dependency_unlock: float
    time_value: float
    financial_cost: float
    risk_penalty: float
    irreversibility_penalty: float
    wip_penalty: float = 0.0

    def score(self) -> float:
        return (
            self.expected_value
            * self.confidence
            * self.dependency_unlock
            * self.time_value
            - self.financial_cost
            - self.risk_penalty
            - self.irreversibility_penalty
            - self.wip_penalty
        )


@dataclasses.dataclass(frozen=True)
class Observation:
    observation_id: str
    action_id: str
    source: str
    payload: Mapping[str, Any]
    observed_at: float


@dataclasses.dataclass(frozen=True)
class VerificationReceipt:
    receipt_id: str
    action_id: str
    status: str
    acceptance_test: str
    observation_hash: str
    issued_at: float
    signature: str = ""

    def payload_bytes(self) -> bytes:
        payload = {
            "receipt_id": self.receipt_id,
            "action_id": self.action_id,
            "status": self.status,
            "acceptance_test": self.acceptance_test,
            "observation_hash": self.observation_hash,
            "issued_at": self.issued_at,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ReceiptSigner:
    def __init__(self, key: bytes):
        if len(key) < 16:
            raise ValueError("receipt key must be at least 16 bytes")
        self._key = key

    def issue(
        self,
        *,
        action_id: str,
        status: str,
        acceptance_test: str,
        observation: Observation,
    ) -> VerificationReceipt:
        obs_hash = hashlib.sha256(
            json.dumps(
                {
                    "observation_id": observation.observation_id,
                    "action_id": observation.action_id,
                    "source": observation.source,
                    "payload": dict(observation.payload),
                    "observed_at": observation.observed_at,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        receipt = VerificationReceipt(
            receipt_id=f"RCPT-{int(time.time() * 1000)}-{secrets.token_hex(4)}",
            action_id=action_id,
            status=status,
            acceptance_test=acceptance_test,
            observation_hash=obs_hash,
            issued_at=time.time(),
        )
        sig = hmac.new(self._key, receipt.payload_bytes(), hashlib.sha256).hexdigest()
        return dataclasses.replace(receipt, signature=sig)

    def verify(self, receipt: VerificationReceipt) -> bool:
        expected = hmac.new(self._key, receipt.payload_bytes(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, receipt.signature)


class AtomicStateStore:
    """Crash-safe JSON state store: tempfile -> fsync -> replace -> directory fsync."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, value: Any) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
            try:
                dir_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return digest


class EventLedger:
    """Append-only SHA-256 chained SQLite event ledger."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL UNIQUE
            )
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def _last_hash(self) -> str:
        row = self.db.execute(
            "SELECT entry_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return "GENESIS" if row is None else row["entry_hash"]

    @staticmethod
    def _entry_hash(
        *,
        event_id: str,
        timestamp: float,
        event_type: str,
        payload: Mapping[str, Any],
        previous_hash: str,
    ) -> str:
        encoded = json.dumps(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "payload": dict(payload),
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def append(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        event_id: str | None = None,
        timestamp: float | None = None,
    ) -> str:
        event_id = event_id or f"EVT-{int(time.time() * 1000)}-{secrets.token_hex(4)}"
        timestamp = time.time() if timestamp is None else timestamp
        payload_json = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))

        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous_hash = self._last_hash()
            entry_hash = self._entry_hash(
                event_id=event_id,
                timestamp=timestamp,
                event_type=event_type,
                payload=json.loads(payload_json),
                previous_hash=previous_hash,
            )
            self.db.execute(
                """
                INSERT INTO events(event_id, timestamp, event_type, payload, previous_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, timestamp, event_type, payload_json, previous_hash, entry_hash),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return entry_hash

    def verify(self) -> tuple[bool, str]:
        rows = self.db.execute("SELECT * FROM events ORDER BY sequence ASC").fetchall()
        expected_previous = "GENESIS"
        for row in rows:
            if row["previous_hash"] != expected_previous:
                return False, f"broken hash chain at sequence {row['sequence']}"
            payload = json.loads(row["payload"])
            expected_hash = self._entry_hash(
                event_id=row["event_id"],
                timestamp=row["timestamp"],
                event_type=row["event_type"],
                payload=payload,
                previous_hash=row["previous_hash"],
            )
            if not hmac.compare_digest(expected_hash, row["entry_hash"]):
                return False, f"corrupted event at sequence {row['sequence']}"
            expected_previous = row["entry_hash"]
        return True, f"verified {len(rows)} events"


class OperatorGovernor:
    def __init__(self, *, max_wip: int = 3):
        if max_wip < 1:
            raise ValueError("max_wip must be >= 1")
        self.max_wip = max_wip
        self.human_stop = False
        self._active: dict[str, Task] = {}

    @property
    def active_tasks(self) -> tuple[Task, ...]:
        return tuple(self._active.values())

    def set_human_stop(self, active: bool) -> None:
        self.human_stop = bool(active)

    def admit(self, task: Task) -> None:
        if self.human_stop:
            raise HumanStopActive("Human STOP is active")
        if task.task_id in self._active:
            return
        if len(self._active) >= self.max_wip:
            raise WIPLimitExceeded("WIP_LIMIT_EXCEEDED")
        task.status = "ACTIVE"
        self._active[task.task_id] = task

    def complete(self, task_id: str, status: str = "VERIFIED") -> Task:
        task = self._active.pop(task_id)
        task.status = status
        return task

    def authorize_task(
        self,
        task: Task,
        *,
        lease: CapabilityLease | None = None,
        approval: HumanApproval | None = None,
        repository: str | None = None,
        pr_number: int | None = None,
        exact_sha: str | None = None,
        now: float | None = None,
    ) -> None:
        if self.human_stop:
            raise HumanStopActive("Human STOP is active")

        if task.required_capability or task.resource:
            if lease is None:
                raise AuthorityDenied("capability lease required")
            if task.required_capability is None or task.resource is None:
                raise AuthorityDenied("task capability/resource contract incomplete")
            if not lease.allows(task.required_capability, task.resource, now):
                raise AuthorityDenied("capability lease does not authorize task")
            if lease.spend_limit is not None and task.budget > lease.spend_limit:
                raise AuthorityDenied("task budget exceeds lease spend limit")

        if task.authority_class >= 3:
            if approval is None:
                raise ApprovalMismatch("explicit human approval required")
            if repository is None or pr_number is None or exact_sha is None:
                raise ApprovalMismatch("exact promotion target required")
            if not approval.authorizes(repository, pr_number, exact_sha, now):
                raise ApprovalMismatch("approval does not match exact target")


class OperatorEngine:
    def __init__(self, governor: OperatorGovernor):
        self.governor = governor

    def rank(self, candidates: Iterable[DecisionCandidate]) -> list[DecisionCandidate]:
        return sorted(candidates, key=lambda c: (c.score(), c.candidate_id), reverse=True)

    def next_candidate(
        self,
        candidates: Iterable[DecisionCandidate],
        tasks: Mapping[str, Task],
    ) -> DecisionCandidate | None:
        if self.governor.human_stop:
            return None
        active_ids = {t.task_id for t in self.governor.active_tasks}
        eligible = [
            candidate
            for candidate in candidates
            if candidate.task_id in tasks
            and tasks[candidate.task_id].status in {"READY", "BLOCKED_HUMAN"}
            and candidate.task_id not in active_ids
        ]
        return self.rank(eligible)[0] if eligible else None
