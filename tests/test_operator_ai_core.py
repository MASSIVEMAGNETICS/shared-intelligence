import dataclasses
import json
from pathlib import Path
import tempfile
import time
import unittest

from operator_ai.core import (
    ApprovalMismatch,
    AtomicStateStore,
    AuthorityDenied,
    CapabilityLease,
    DecisionCandidate,
    EventLedger,
    HumanApproval,
    HumanStopActive,
    Observation,
    OperatorEngine,
    OperatorGovernor,
    ReceiptSigner,
    Task,
    WIPLimitExceeded,
)


def _task(i: int, authority_class: int = 1) -> Task:
    return Task(
        task_id=f"T{i}",
        objective_id="OBJ-1",
        title=f"Task {i}",
        authority_class=authority_class,
        terminal_condition="done",
        acceptance_test="verified observation exists",
    )


class OperatorAITests(unittest.TestCase):
    def test_wip_limit_enforced(self):
        g = OperatorGovernor(max_wip=3)
        for i in range(3):
            g.admit(_task(i))
        with self.assertRaises(WIPLimitExceeded):
            g.admit(_task(3))

    def test_human_stop_fails_closed(self):
        g = OperatorGovernor(max_wip=3)
        g.set_human_stop(True)
        with self.assertRaises(HumanStopActive):
            g.admit(_task(1))

    def test_lease_scope_and_spend_limit(self):
        now = time.time()
        lease = CapabilityLease(
            lease_id="L1",
            capabilities=frozenset({"send_email"}),
            resources=frozenset({"crm:lead:123"}),
            issued_at=now - 1,
            expires_at=now + 60,
            spend_limit=25.0,
        )
        task = Task(
            task_id="T1",
            objective_id="O1",
            title="Follow up",
            authority_class=2,
            required_capability="send_email",
            resource="crm:lead:123",
            budget=0.0,
        )
        OperatorGovernor().authorize_task(task, lease=lease, now=now)

        bad = Task(
            task_id="T2",
            objective_id="O1",
            title="Wrong resource",
            authority_class=2,
            required_capability="send_email",
            resource="crm:lead:999",
        )
        with self.assertRaises(AuthorityDenied):
            OperatorGovernor().authorize_task(bad, lease=lease, now=now)

    def test_exact_sha_human_approval(self):
        now = time.time()
        approval = HumanApproval(
            approval_id="A1",
            issued_by="Bando",
            repository="MASSIVEMAGNETICS/shared-intelligence",
            pr_number=2,
            exact_sha="abc123",
            issued_at=now - 1,
        )
        task = _task(9, authority_class=3)
        g = OperatorGovernor()

        g.authorize_task(
            task,
            approval=approval,
            repository="MASSIVEMAGNETICS/shared-intelligence",
            pr_number=2,
            exact_sha="abc123",
            now=now,
        )

        with self.assertRaises(ApprovalMismatch):
            g.authorize_task(
                task,
                approval=approval,
                repository="MASSIVEMAGNETICS/shared-intelligence",
                pr_number=2,
                exact_sha="changed",
                now=now,
            )

    def test_atomic_state_store_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            store = AtomicStateStore(path)
            digest = store.save({"wip": ["T1", "T2"], "version": 1})
            self.assertEqual(len(digest), 64)
            self.assertEqual(store.load(), {"version": 1, "wip": ["T1", "T2"]})

    def test_ledger_integrity_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.db"
            ledger = EventLedger(path)
            try:
                ledger.append("TASK_ADMITTED", {"task_id": "T1"}, event_id="E1", timestamp=1.0)
                ledger.append("VERIFICATION_PASSED", {"task_id": "T1"}, event_id="E2", timestamp=2.0)
                ok, msg = ledger.verify()
                self.assertTrue(ok, msg)

                ledger.db.execute(
                    "UPDATE events SET payload = ? WHERE event_id = ?",
                    (json.dumps({"task_id": "MUTATED"}), "E1"),
                )
                ledger.db.commit()
                ok, _ = ledger.verify()
                self.assertFalse(ok)
            finally:
                ledger.close()

    def test_receipt_signature_detects_tamper(self):
        signer = ReceiptSigner(b"0123456789abcdef0123456789abcdef")
        obs = Observation(
            observation_id="OBS1",
            action_id="ACT1",
            source="github",
            payload={"merged": True, "sha": "abc"},
            observed_at=1.0,
        )
        receipt = signer.issue(
            action_id="ACT1",
            status="VERIFIED_SUCCESS",
            acceptance_test="merged == true",
            observation=obs,
        )
        self.assertTrue(signer.verify(receipt))
        mutated = dataclasses.replace(receipt, status="VERIFIED_FAILURE")
        self.assertFalse(signer.verify(mutated))

    def test_engine_ranks_expected_value_and_cost(self):
        g = OperatorGovernor()
        engine = OperatorEngine(g)
        tasks = {"T1": _task(1), "T2": _task(2)}
        candidates = [
            DecisionCandidate("C1", "T1", 100, 0.5, 1, 1, 10, 2, 1),
            DecisionCandidate("C2", "T2", 90, 0.9, 1, 1, 5, 2, 1),
        ]
        self.assertEqual(engine.next_candidate(candidates, tasks).candidate_id, "C2")


if __name__ == "__main__":
    unittest.main()
