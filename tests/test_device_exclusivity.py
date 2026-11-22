"""Acquire-only device exclusivity in the local Core + Edge reference.

These tests establish simulated authorization behavior, not OEM completion or
Core/Edge restart reconciliation.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
import multiprocessing
import sqlite3
import threading
import unittest
from unittest.mock import patch

from reference.runtime_core import CoreDenied, RuntimeCore
from reference.edge_fence import EdgeFenceState
import test_runtime_core as fixtures


def _acquire_from_process(path, session_id, start, results):
    """Spawn-compatible worker: separate Core process, shared durable store."""
    core = RuntimeCore(path, trusted_clock=lambda: fixtures.BASE)
    start.wait(timeout=10)
    try:
        core.acquire_device(session_id, "device-admin")
        results.put((session_id, "acquired"))
    except CoreDenied as error:
        results.put((session_id, error.reason))


class TestDeviceExclusivity(unittest.TestCase):
    # Reuse only fixtures/helpers, not TestRuntimeCore's test methods.
    setUp = fixtures.TestRuntimeCore.setUp
    grant = fixtures.TestRuntimeCore.grant
    policy = fixtures.TestRuntimeCore.policy
    compliance = fixtures.TestRuntimeCore.compliance
    start = fixtures.TestRuntimeCore.start
    lease = fixtures.TestRuntimeCore.lease
    pump = fixtures.TestRuntimeCore.pump
    command = fixtures.TestRuntimeCore.command
    assertReason = fixtures.TestRuntimeCore.assertReason

    def second_session(self, session_id="session-2", edge_id="edge-1", *, active=True,
                       grant_overrides=None):
        grant_id = "grant-" + session_id
        self.core.provision_grant(self.grant(grant_id=grant_id, **(grant_overrides or {})))
        self.core.create_session(session_id, "owner-1", "twin-1", [grant_id], edge_id)
        self.core.set_policies(
            session_id,
            self.policy(policy_id="policy-" + session_id, session_id=session_id),
            self.compliance(policy_id="compliance-" + session_id, session_id=session_id),
        )
        self.core.prepare_session(session_id)
        if active:
            self.core.activate_session(session_id, "autonomous")
        return grant_id

    def assert_held(self, session_id="session-1", epoch=1, edge_id="edge-1"):
        slot = self.core.device_slot(edge_id)
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("held", session_id, epoch))

    def assert_quarantined(self, principal="device-admin"):
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("quarantined", "session-1", 1))
        self.assertReason("device_state_unverified", self.core.acquire_device,
                          "session-1", principal)
        self.assertReason("device_state_unverified", self.lease)
        self.assertReason("device_state_unverified", self.core.change_mode,
                          "session-1", "autonomous")
        self.assertReason("device_state_unverified", self.core.activate_session,
                          "session-1", "autonomous")

    def test_unclassified_edge_defaults_to_physical(self):
        self.start(acquire_device=False)
        self.assertReason("device_not_acquired", self.lease)
        self.core.acquire_device("session-1", "device-admin")
        self.assertEqual(self.lease()["device_epoch"], 1)

    def test_unknown_execution_class_treated_as_physical(self):
        for index, execution_class in enumerate(("unknown", "Digital", "")):
            with self.subTest(execution_class=execution_class):
                edge_id, session_id = f"edge-{index + 2}", f"session-{index + 2}"
                self.core.register_edge(edge_id, "boot-1", ["conversation"],
                                        execution_class=execution_class,
                                        acquire_principal_id="device-admin")
                grant_id = self.second_session(session_id, edge_id)
                self.assertReason("device_not_acquired", self.core.issue_lease,
                                  session_id, "ai-1", "ai-1", "conversation", grant_id)

    def test_device_acquire_permission_is_separate_from_session_policy(self):
        self.start(acquire_device=False)
        for controller in ("ai-1", "owner-controller"):
            with self.subTest(controller=controller):
                self.assertReason("device_acquire_not_authorized", self.core.acquire_device,
                                  "session-1", controller)
        for principal in (None, ""):
            with self.subTest(principal=principal):
                self.assertReason("principal_not_authenticated", self.core.acquire_device,
                                  "session-1", principal)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "free")
        self.core.acquire_device("session-1", "device-admin")
        self.assert_held()
        self.assertReason("controller_not_authorized", self.core.issue_lease,
                          "session-1", "device-admin", "device-admin", "conversation", "grant-1")

    def _assert_invalid_grant_denies_free_device(self):
        self.assertReason("no_valid_representation_authority", self.core.acquire_device,
                          "session-1", "device-admin")
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("free", None, 0))
        events = self.core.device_events("edge-1")
        self.assertEqual([(e["status"], e["reason"]) for e in events],
                         [("denied", "no_valid_representation_authority")])
        self.assertEqual(events[0]["session_id"], "session-1")
        self.assertEqual(self.core.pending_edge_updates("edge-1"), [])
        # A different Session with a Grant valid at the current simulated time
        # must still be able to acquire the device, starting with epoch 1.
        self.second_session(active=False, grant_overrides={
            "valid_from": fixtures.iso(self.clock.now - timedelta(minutes=1)),
            "valid_until": fixtures.iso(self.clock.now + timedelta(minutes=30)),
        })
        self.core.acquire_device("session-2", "device-admin")
        self.assert_held("session-2")
        self.assertEqual([e["status"] for e in self.core.device_events("edge-1")],
                         ["denied", "acquired"])

    def test_acquire_requires_currently_valid_grant_revoked_ready(self):
        self.core.revoke_grant("grant-1")
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ready")
        self._assert_invalid_grant_denies_free_device()

    def test_acquire_requires_currently_valid_grant_expired_ready(self):
        self.clock.advance(31 * 60)
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ready")
        self._assert_invalid_grant_denies_free_device()

    def test_acquire_requires_currently_valid_grant_expired_active(self):
        self.start(acquire_device=False)
        self.clock.advance(31 * 60)
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "active")
        self._assert_invalid_grant_denies_free_device()

    def test_physical_registration_requires_explicit_device_acquirer(self):
        self.assertReason("device_acquirer_unconfigured", self.core.register_edge,
                          "edge-unconfigured", "boot-1", ["conversation"])

    def test_acquire_ready_session_is_idempotent_and_does_not_issue_authority(self):
        first = self.core.acquire_device("session-1", "device-admin")
        second = self.core.acquire_device("session-1", "device-admin")
        self.assertEqual(first, second)
        self.assert_held()
        self.assertEqual(self.core.pending_edge_updates("edge-1"), [])
        self.assertEqual(self.core.active_leases("session-1"), [])
        self.assertEqual([e["status"] for e in self.core.device_events("edge-1")], ["acquired"])

    def test_second_session_acquire_denied_device_busy(self):
        self.start()
        self.second_session()
        self.assertReason("device_busy", self.core.acquire_device, "session-2", "device-admin")
        self.assert_held()

    def test_second_session_different_domain_still_busy(self):
        self.start()
        self.lease(domain="conversation")
        grant_id = self.second_session()
        self.assertReason("device_busy", self.core.acquire_device, "session-2", "device-admin")
        self.assertReason("device_busy", self.core.issue_lease,
                          "session-2", "ai-1", "ai-1", "gesture", grant_id)
        self.assertEqual(self.core.active_leases("session-2"), [])
        self.assert_held()

    def test_lease_without_slot_denied_no_outbox_no_audit(self):
        self.start(acquire_device=False)
        before_events = self.core.events("session-1")
        self.assertReason("device_not_acquired", self.lease)
        self.assertEqual(self.core.events("session-1"), before_events)
        self.assertEqual(self.core.pending_edge_updates("edge-1"), [])
        self.assertEqual(self.core.active_leases("session-1"), [])
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["device_epoch"]), ("free", 0))

    def test_concurrent_acquire_two_core_instances_single_holder(self):
        self.start(acquire_device=False)
        self.second_session()
        other_core = RuntimeCore(self.path, trusted_clock=self.clock.wall)
        start = threading.Barrier(2)

        def acquire(core, session_id):
            start.wait(timeout=10)
            try:
                core.acquire_device(session_id, "device-admin")
                return session_id, "acquired"
            except CoreDenied as error:
                return session_id, error.reason

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(acquire, self.core, "session-1"),
                       executor.submit(acquire, other_core, "session-2")]
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual([status for _, status in results], ["acquired", "device_busy"])
        holder = next(session for session, status in results if status == "acquired")
        self.assert_held(holder)
        self.assertEqual([e["status"] for e in self.core.device_events("edge-1")],
                         ["acquired", "denied"])

    def test_concurrent_acquire_separate_processes_single_holder(self):
        self.start(acquire_device=False)
        self.second_session()
        context = multiprocessing.get_context("spawn")
        start, results_queue = context.Barrier(2), context.Queue()
        processes = [
            context.Process(target=_acquire_from_process,
                            args=(str(self.path), session, start, results_queue))
            for session in ("session-1", "session-2")
        ]
        try:
            for process in processes:
                process.start()
            results = [results_queue.get(timeout=20) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            self.assertCountEqual([status for _, status in results], ["acquired", "device_busy"])
            holder = next(session for session, status in results if status == "acquired")
            self.assert_held(holder)
        finally:
            for process in processes:
                if process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=5)
                    process.close()
            results_queue.close()
            results_queue.join_thread()

    def test_acquire_rolls_back_if_device_audit_raises(self):
        with patch.object(self.core, "_device_audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.core.acquire_device("session-1", "device-admin")
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("free", None, 0))
        self.assertEqual(self.core.device_events("edge-1"), [])
        self.core.acquire_device("session-1", "device-admin")
        self.assert_held()

    def test_reboot_with_free_slot_keeps_free_state(self):
        self.core.register_edge("edge-1", "boot-2", ["conversation", "gesture"],
                                acquire_principal_id="device-admin")
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("free", None, 0))
        self.assertEqual(self.core.device_events("edge-1"), [])
        self.core.activate_session("session-1", "autonomous")
        self.core.acquire_device("session-1", "device-admin")
        self.assert_held()

    def test_held_reregistration_non_digital_spellings_keeps_physical(self):
        self.start()
        for execution_class in ("DIGITAL", " digital", "digital ", "Digital"):
            with self.subTest(execution_class=execution_class):
                self.core.register_edge(
                    "edge-1", "boot-1", ["conversation", "gesture"],
                    execution_class=execution_class, acquire_principal_id="device-admin"
                )
                self.assert_held()
                self.assertEqual(self.core.session_snapshot("session-1")["session_status"],
                                 "active")
        self.assertEqual([e["status"] for e in self.core.device_events("edge-1")],
                         ["acquired"])

    def test_core_physical_edge_digital_mismatch_still_rejects_second_session(self):
        self.start()
        lease = self.lease()
        mismatched_edge = EdgeFenceState(
            "edge-1", "boot-1", execution_class="digital",
            supported_control_domains=["conversation", "gesture"],
            monotonic_clock=self.clock.monotonic,
            trusted_wall_clock=self.clock.wall,
        )
        for _, message in self.core.pending_edge_updates("edge-1"):
            self.assertEqual(mismatched_edge.install_authority(message),
                             (True, "accepted"))
        self.second_session()
        self.assertReason("device_busy", self.core.acquire_device, "session-2", "device-admin")
        self.assertReason("device_busy", self.core.issue_lease,
                          "session-2", "ai-1", "ai-1", "conversation",
                          "grant-session-2")
        self.assert_held()
        # This tests Core exclusivity only, NOT correct Edge provisioning.
        self.assertEqual(mismatched_edge.check_command(self.command(lease), "ai-1"),
                         (True, "accepted"))

    def test_slot_and_epoch_survive_core_restart(self):
        self.start()
        self.second_session()
        before = self.core.device_slot("edge-1")
        restarted = RuntimeCore(self.path, trusted_clock=self.clock.wall)
        self.assertEqual(restarted.device_slot("edge-1"), before)
        self.assertReason("device_busy", restarted.acquire_device, "session-2", "device-admin")
        # Persistence alone does not implement RFC-0004 Core/Edge reconciliation.
        self.assertEqual(restarted.device_slot("edge-1"), before)

    def test_mode_change_keeps_slot_and_epoch(self):
        self.start()
        previous = self.lease()
        self.pump()
        for mode, controller in (("bridge", "owner-controller"),
                                 ("totalmersion", "owner-controller"),
                                 ("autonomous", "ai-1")):
            self.core.change_mode("session-1", mode, owner_presence_confirmed=mode != "autonomous")
            current = self.lease(controller)
            self.assertGreater(current["generation"], previous["generation"])
            self.assertEqual(current["device_epoch"], 1)
            self.assert_held()
            self.assertTrue(all(result == (True, "accepted") for _, result in self.pump()))
            self.assertFalse(self.edge.check_command(self.command(previous), previous["controller_id"])[0])
            self.assertEqual(self.edge.check_command(self.command(current), controller), (True, "accepted"))
            previous = current
        statuses = [e["status"] for e in self.core.device_events("edge-1")]
        self.assertEqual(statuses.count("acquired"), 1)
        self.assertIn("fallback", statuses)

    def test_suspend_disconnect_revoke_do_not_release_slot(self):
        self.start("totalmersion")
        self.second_session()
        operations = [
            lambda: self.core.owner_disconnected("session-1"),
            lambda: self.core.revoke_session_control("session-1"),
            lambda: self.core.set_policies("session-1", self.policy(version="2"), self.compliance()),
            lambda: self.core.revoke_grant("grant-1"),
        ]
        for operation in operations:
            if self.core.session_snapshot("session-1")["session_status"] == "suspended":
                self.core.activate_session("session-1", "totalmersion", owner_presence_confirmed=True)
            self.lease("owner-controller")
            operation()
            self.assert_held()
            self.assertReason("device_busy", self.core.acquire_device, "session-2", "device-admin")

    def test_lease_expiry_does_not_release_slot(self):
        self.start()
        lease = self.lease()
        self.pump()
        self.second_session()
        self.clock.advance(31)
        self.assertEqual(self.edge.check_command(self.command(lease), "ai-1"), (False, "expired"))
        self.assert_held()
        self.assertReason("device_busy", self.core.acquire_device, "session-2", "device-admin")

    def test_edge_reboot_quarantines_held_slot(self):
        self.start()
        self.lease()
        self.core.register_edge("edge-1", "boot-2", ["conversation", "gesture"],
                                acquire_principal_id="device-admin")
        self.assert_quarantined()
        self.assertEqual(self.core.active_leases("session-1"), [])
        self.assertEqual(self.core.device_events("edge-1")[-1]["status"], "denied")
        self.assertIn("quarantined", [e["status"] for e in self.core.device_events("edge-1")])

    def test_reclassification_quarantines_held_slot_even_when_digital(self):
        self.start()
        self.lease()
        self.core.register_edge("edge-1", "boot-1", ["conversation", "gesture"],
                                execution_class="digital", acquire_principal_id="device-admin")
        self.assert_quarantined()
        # Re-registration cannot reset the quarantine or create a new free slot.
        self.core.register_edge("edge-1", "boot-1", ["conversation", "gesture"],
                                execution_class="digital", acquire_principal_id="device-admin")
        self.assert_quarantined()

    def test_acquirer_change_quarantines_held_slot(self):
        self.start()
        self.core.register_edge("edge-1", "boot-1", ["conversation", "gesture"],
                                acquire_principal_id="replacement-admin")
        self.assert_quarantined("replacement-admin")

    def test_install_and_revoke_payloads_carry_device_epoch(self):
        self.start()
        lease = self.lease()
        self.assertEqual(lease["device_epoch"], 1)
        self.core.revoke_session_control("session-1")
        messages = [message for _, message in self.core.pending_edge_updates("edge-1")]
        self.assertEqual([m["kind"] for m in messages], ["edge.authority_install", "edge.authority_revoke"])
        self.assertTrue(all(m["device_epoch"] == 1 and m["session_id"] == "session-1" for m in messages))

    def test_device_audit_strictly_ordered_no_effective(self):
        self.start("bridge")
        self.second_session()
        self.assertReason("device_busy", self.core.acquire_device, "session-2", "device-admin")
        self.core.change_mode("session-1", "autonomous")
        self.core.register_edge("edge-1", "boot-2", ["conversation", "gesture"],
                                acquire_principal_id="device-admin")
        events = self.core.device_events("edge-1")
        self.assertEqual([e["device_sequence"] for e in events], list(range(1, len(events) + 1)))
        self.assertEqual([e["status"] for e in events], ["acquired", "denied", "fallback", "quarantined"])
        self.assertTrue(all(e["edge_id"] == "edge-1" and e["device_epoch"] == 1 for e in events))
        self.assertTrue(all(e["reason"] and e["correlation_id"] and e["edge_boot_id"] for e in events))
        self.assertNotIn("effective", [e["status"] for e in events])
        self.assertEqual(events[1]["session_id"], "session-2")
        self.assertEqual(events[1]["prior_session_id"], "session-1")
        mode_changes = [e for e in self.core.events("session-1")
                        if e["event_type"] == "presence_mode.changed"
                        and e["data"].get("from_mode") == "bridge"
                        and e["data"].get("to_mode") == "autonomous"]
        self.assertEqual(events[2]["correlation_id"], mode_changes[0]["correlation_id"])

    def test_bridge_two_controllers_same_session_still_works(self):
        self.start("bridge")
        ai, owner = self.lease("ai-1", "conversation"), self.lease("owner-controller", "gesture")
        self.assertTrue(all(result == (True, "accepted") for _, result in self.pump()))
        self.assertEqual(self.edge.check_command(self.command(ai), "ai-1"), (True, "accepted"))
        self.assertEqual(self.edge.check_command(self.command(owner), "owner-controller"), (True, "accepted"))
        self.assertEqual(len(self.core.active_leases("session-1")), 2)
        self.assert_held()

    def test_two_physical_edges_independent_sessions(self):
        self.start()
        self.core.register_edge("edge-2", "boot-2", ["conversation"],
                                acquire_principal_id="device-admin")
        grant_id = self.second_session(edge_id="edge-2")
        self.core.acquire_device("session-2", "device-admin")
        first = self.lease()
        second = self.core.issue_lease("session-2", "ai-1", "ai-1", "conversation", grant_id)
        self.pump()
        other_edge = EdgeFenceState("edge-2", "boot-2", supported_control_domains=["conversation"],
                                   monotonic_clock=self.clock.monotonic,
                                   trusted_wall_clock=self.clock.wall)
        for _, message in self.core.pending_edge_updates("edge-2"):
            self.assertEqual(other_edge.install_authority(message), (True, "accepted"))
        self.assertEqual(self.edge.check_command(self.command(first), "ai-1"), (True, "accepted"))
        self.assertEqual(other_edge.check_command(self.command(second), "ai-1"), (True, "accepted"))
        self.assert_held()
        self.assert_held("session-2", edge_id="edge-2")

    def test_digital_edge_allows_concurrent_sessions_without_device_epoch(self):
        self.core.register_edge("edge-1", "boot-1", ["conversation", "gesture"], execution_class="digital")
        self.edge = EdgeFenceState("edge-1", "boot-1", execution_class="digital",
                                   supported_control_domains=["conversation", "gesture"],
                                   monotonic_clock=self.clock.monotonic,
                                   trusted_wall_clock=self.clock.wall)
        self.start(acquire_device=False)
        grant_id = self.second_session()
        first = self.lease()
        second = self.core.issue_lease("session-2", "ai-1", "ai-1", "conversation", grant_id)
        self.assertNotIn("device_epoch", first)
        self.assertNotIn("device_epoch", second)
        self.assertTrue(all(result == (True, "accepted") for _, result in self.pump()))
        self.assertEqual(self.edge.check_command(self.command(first), "ai-1"), (True, "accepted"))
        self.assertEqual(self.edge.check_command(self.command(second), "ai-1"), (True, "accepted"))
        self.assertReason("device_slot_not_required", self.core.acquire_device, "session-1", "device-admin")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "free")

    def test_legacy_database_fails_closed_without_silent_migration(self):
        path = self.path.with_name("legacy.sqlite")
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE edges (edge_id TEXT PRIMARY KEY, boot_id TEXT NOT NULL, domains TEXT NOT NULL)")
            db.execute("INSERT INTO edges VALUES ('edge-old', 'boot-old', '[\"conversation\"]')")
        self.assertReason("database_upgrade_required", RuntimeCore, path, trusted_clock=self.clock.wall)
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual([row[1] for row in db.execute("PRAGMA table_info(edges)")],
                             ["edge_id", "boot_id", "domains"])
            self.assertEqual(db.execute("SELECT edge_id FROM edges").fetchall(), [("edge-old",)])
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='device_slots'").fetchall(), [])

    def test_missing_device_table_is_not_recreated_on_restart(self):
        self.start()
        self.lease()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE device_slots")
        self.assertReason("database_upgrade_required", RuntimeCore, self.path,
                          trusted_clock=self.clock.wall)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='device_slots'").fetchall(), [])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 1)

    def test_missing_device_slot_is_not_reset_by_reregistration(self):
        self.start()
        self.lease()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM device_slots WHERE edge_id='edge-1'")
        self.assertReason("unknown_device_slot", self.core.register_edge,
                          "edge-1", "boot-2", ["conversation", "gesture"],
                          acquire_principal_id="device-admin")
        self.assertReason("unknown_device_slot", self.core.acquire_device, "session-1", "device-admin")
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM device_slots").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT boot_id FROM edges WHERE edge_id='edge-1'").fetchone()[0], "boot-1")

    def test_missing_edge_registration_is_not_recreated_over_retained_authority(self):
        self.start()
        lease = self.lease()
        slot = self.core.device_slot("edge-1")
        events = self.core.device_events("edge-1")
        updates = self.core.pending_edge_updates("edge-1")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM edges WHERE edge_id='edge-1'")
        self.assertReason("device_state_unverified", self.core.register_edge,
                          "edge-1", "boot-2", ["conversation", "gesture"],
                          acquire_principal_id="device-admin")
        self.assertEqual(self.core.device_slot("edge-1"), slot)
        self.assert_held()
        self.assertEqual(self.core.device_events("edge-1"), events)
        self.assertEqual(self.core.active_leases("session-1"), [lease])
        self.assertEqual(self.core.pending_edge_updates("edge-1"), updates)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT edge_id FROM edges WHERE edge_id='edge-1'").fetchall(), [])
            self.assertEqual(db.execute("SELECT boot_id FROM edge_boot_history WHERE edge_id='edge-1'").fetchall(),
                             [("boot-1",)])


if __name__ == "__main__":
    unittest.main()
