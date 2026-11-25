"""Terminal Session end in the simulated reference; no physical completion claim."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
import threading
import unittest
from unittest.mock import patch

import test_runtime_core as runtime
import test_device_exclusivity as devices
from reference.runtime_core import CoreDenied, RuntimeCore


class TestSessionEnd(unittest.TestCase):
    setUp = runtime.TestRuntimeCore.setUp
    grant = runtime.TestRuntimeCore.grant
    policy = runtime.TestRuntimeCore.policy
    compliance = runtime.TestRuntimeCore.compliance
    start = runtime.TestRuntimeCore.start
    lease = runtime.TestRuntimeCore.lease
    pump = runtime.TestRuntimeCore.pump
    command = runtime.TestRuntimeCore.command
    assertReason = runtime.TestRuntimeCore.assertReason
    second_session = devices.TestDeviceExclusivity.second_session

    def test_explicit_end_authority_is_separate_and_idempotent(self):
        self.start()
        self.lease()
        self.assertReason("session_end_not_authorized", self.core.end_session, "session-1", "device-admin")
        self.core.provision_session_end("session-1", "session-ender")
        self.core.provision_session_end("session-1", "session-ender")
        self.assertReason("session_end_principal_immutable", self.core.provision_session_end,
                          "session-1", "another")
        for actor in ("device-admin", "ai-1", "owner-controller", "owner-1"):
            self.assertReason("session_end_not_authorized", self.core.end_session, "session-1", actor)
        self.assertReason("principal_not_authenticated", self.core.end_session, "session-1", "")
        self.assertEqual(len(self.core.active_leases("session-1")), 1)
        self.core.end_session("session-1", "session-ender")
        events = self.core.events("session-1")
        slot = self.core.device_slot("edge-1")
        device_events = self.core.device_events("edge-1")
        self.core.end_session("session-1", "session-ender")
        self.assertEqual(self.core.events("session-1"), events)
        self.assertEqual(self.core.device_slot("edge-1"), slot)
        self.assertEqual(self.core.device_events("edge-1"), device_events)
        self.assertReason("session_end_not_authorized", self.core.end_session, "session-1", "another")
        self.assertEqual(sum(e["event_type"] == "session.ended" for e in events), 1)

    def test_end_denials_commit_correlated_audit_without_mutating_authority(self):
        self.start()
        self.lease()
        before = (self.core.device_slot("edge-1"), self.core.session_snapshot("session-1"),
                  self.core.active_leases("session-1"), self.core.pending_edge_updates("edge-1"))
        cases = [("intruder", "session_end_not_authorized"),
                 ("", "principal_not_authenticated"),
                 (None, "principal_not_authenticated"),
                 (123, "principal_not_authenticated")]
        def assert_denial(actor, reason):
            device_before = self.core.device_events("edge-1")
            session_before = self.core.events("session-1")
            self.assertReason(reason, self.core.end_session, "session-1", actor)
            de = self.core.device_events("edge-1")
            se = self.core.events("session-1")
            self.assertEqual(de[:-1], device_before)
            self.assertEqual(se[:-1], session_before)
            self.assertEqual((de[-1]["status"], de[-1]["reason"]), ("denied", reason))
            self.assertEqual(se[-1]["event_type"], "session.end_denied")
            self.assertEqual(se[-1]["data"]["reason"], reason)
            self.assertEqual(de[-1]["correlation_id"], se[-1]["correlation_id"])
            self.assertEqual(de[-1]["session_id"], "session-1")
            self.assertEqual(de[-1]["prior_session_id"], "session-1")
            expected_class = "authenticated_principal" if isinstance(actor, str) and actor else "unauthenticated"
            self.assertEqual(de[-1]["actor_class"], expected_class)
            self.assertEqual(se[-1]["data"]["actor_class"], expected_class)
            if expected_class == "unauthenticated":
                self.assertNotIn("actor_id", de[-1])
                self.assertNotIn("actor_id", se[-1]["data"])
            else:
                self.assertEqual(de[-1]["actor_id"], actor)
                self.assertEqual(se[-1]["data"]["actor_id"], actor)
            self.assertEqual(before, (self.core.device_slot("edge-1"), self.core.session_snapshot("session-1"),
                                     self.core.active_leases("session-1"), self.core.pending_edge_updates("edge-1")))
        for actor, reason in cases:
            assert_denial(actor, reason)
        self.core.provision_session_end("session-1", "ender")
        assert_denial("intruder", "session_end_not_authorized")
        assert_denial("", "principal_not_authenticated")
        # Read through a fresh SQLite connection to prove the denial was committed.
        with closing(sqlite3.connect(self.path)) as db:
            stored = db.execute("SELECT COUNT(*) FROM device_events WHERE edge_id=?", ("edge-1",)).fetchone()[0]
            self.assertEqual(stored, len(self.core.device_events("edge-1")))
        self.core.end_session("session-1", "ender")
        count = len(self.core.events("session-1"))
        self.assertReason("session_end_not_authorized", self.core.end_session, "session-1", "intruder")
        self.assertEqual(len(self.core.events("session-1")), count + 1)
        self.assertEqual(self.core.events("session-1")[-1]["event_type"], "session.end_denied")

    def test_end_denials_for_digital_session_and_unknown_session(self):
        self.core.register_edge("digital-edge", "boot-1", ["conversation"], execution_class="digital")
        self.second_session("digital-session", "digital-edge")
        before = self.core.events("digital-session")
        self.assertReason("session_end_not_authorized", self.core.end_session, "digital-session", "intruder")
        after = self.core.events("digital-session")
        self.assertEqual(after[:-1], before)
        self.assertEqual(after[-1]["event_type"], "session.end_denied")
        self.assertEqual(self.core.device_events("digital-edge"), [])
        self.assertEqual(self.core.device_slot("digital-edge")["state"], "free")
        self.assertReason("unknown_session", self.core.end_session, "unknown", "intruder")
        self.assertReason("principal_not_authenticated", self.core.end_session, "unknown", "")
        self.assertEqual(self.core.events("digital-session"), after)
        self.assertEqual(self.core.device_events("digital-edge"), [])

    def test_end_denial_audit_failure_rolls_back_both_events(self):
        self.start()
        self.lease()
        before = (self.core.events("session-1"), self.core.device_events("edge-1"),
                  self.core.device_slot("edge-1"), self.core.active_leases("session-1"))
        with patch.object(self.core, "_device_audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.core.end_session("session-1", "intruder")
        self.assertEqual(before, (self.core.events("session-1"), self.core.device_events("edge-1"),
                                  self.core.device_slot("edge-1"), self.core.active_leases("session-1")))

    def test_partial_lifecycle_schema_is_rejected_before_use(self):
        self.start()
        self.core.close()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("ALTER TABLE device_slots RENAME TO lifecycle_slots")
            db.execute("""CREATE TABLE device_slots (
                edge_id TEXT PRIMARY KEY, state TEXT NOT NULL CHECK(state IN ('free','held','quarantined')),
                session_id TEXT, device_epoch INTEGER NOT NULL CHECK(device_epoch>=0),
                reason TEXT, updated_at TEXT NOT NULL,
                transfer_deadline TEXT, fence_boot_id TEXT, fence_correlation_id TEXT)""")
            db.execute("INSERT INTO device_slots SELECT * FROM lifecycle_slots")
            db.execute("DROP TABLE lifecycle_slots")
        self.assertReason("database_upgrade_required", RuntimeCore, self.path, trusted_clock=self.clock.wall)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT state FROM device_slots WHERE edge_id='edge-1'").fetchone()[0], "held")

    def test_database_trigger_rejects_reopening_ended_session(self):
        self.core.provision_session_end("session-1", "ender")
        self.core.end_session("session-1", "ender")
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "session_ended"):
                db.execute("UPDATE sessions SET status='active' WHERE session_id='session-1'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "session_ended"):
                db.execute("UPDATE sessions SET presence_mode='bridge' WHERE session_id='session-1'")
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ended")

    def test_holder_end_revokes_all_domains_and_never_frees(self):
        self.start("bridge")
        self.second_session()
        first = self.lease("ai-1", "conversation")
        second = self.lease("owner-controller", "gesture")
        self.pump()
        self.assertTrue(self.edge.check_command(self.command(first), "ai-1")[0])
        self.assertTrue(self.edge.check_command(self.command(second), "owner-controller")[0])
        self.lease("owner-controller", "conversation")  # pending replacement
        self.core.provision_session_end("session-1", "ender")
        self.core.end_session("session-1", "ender")
        state = self.core.session_snapshot("session-1")
        self.assertEqual(state["session_status"], "ended")
        self.assertIsNone(state["presence_mode"])
        self.assertEqual(self.core.active_leases("session-1"), [])
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("transferring", "session-1", 2))
        self.assertEqual(slot["fence_boot_id"], "boot-1")
        self.assertEqual(slot["transfer_deadline"], runtime.iso(self.clock.now + runtime.timedelta(seconds=30)))
        updates = self.core.pending_edge_updates("edge-1")
        self.assertTrue(updates)
        self.assertTrue(all(m["kind"] == "edge.authority_revoke" and m["device_epoch"] == 1 for _, m in updates))
        self.pump()
        self.assertFalse(self.edge.check_command(self.command(first), "ai-1")[0])
        self.assertFalse(self.edge.check_command(self.command(second), "owner-controller")[0])
        self.assertEqual(self.core.device_slot("edge-1"), slot)
        self.assertReason("device_transfer_pending", self.core.acquire_device, "session-2", "device-admin")
        self.assertReason("device_transfer_pending", self.core.issue_lease,
                          "session-2", "ai-1", "ai-1", "conversation", "grant-session-2")
        events = self.core.device_events("edge-1")
        requests = [e for e in events if e["status"] in ("release_requested", "fence_requested")]
        self.assertEqual([e["status"] for e in requests], ["release_requested", "fence_requested"])
        self.assertTrue(all(e["correlation_id"] == slot["fence_correlation_id"] and e["actor_id"] == "ender"
                            for e in requests))
        self.assertNotIn("released", [e["status"] for e in events])
        self.assertNotIn("effective", [e["status"] for e in events])
        self.assertEqual(self.core.events("session-1")[-1]["correlation_id"], slot["fence_correlation_id"])

    def test_ended_session_cannot_resume_or_reacquire(self):
        self.core.provision_session_end("session-1", "ender")
        self.core.end_session("session-1", "ender")
        for fn, args in (
            (self.core.prepare_session, ("session-1",)),
            (self.core.activate_session, ("session-1", "autonomous")),
            (self.core.change_mode, ("session-1", "bridge")),
            (self.core.acquire_device, ("session-1", "device-admin")),
            (self.core.issue_lease, ("session-1", "ai-1", "ai-1", "conversation", "grant-1")),
            (self.core.set_policies, ("session-1", self.policy(), self.compliance())),
            (self.core.provision_session_end, ("session-1", "ender")),
        ):
            self.assertReason("session_ended", fn, *args)
        self.assertReason("session_already_exists", self.core.create_session,
                          "session-1", "owner-1", "twin-1", ["grant-1"], "edge-1")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "free")

    def test_nonholder_end_preserves_current_holder(self):
        self.start()
        self.lease()
        self.second_session()
        slot = self.core.device_slot("edge-1")
        leases = self.core.active_leases("session-1")
        self.core.provision_session_end("session-2", "ender-2")
        self.core.end_session("session-2", "ender-2")
        self.assertEqual(self.core.device_slot("edge-1"), slot)
        self.assertEqual(self.core.active_leases("session-1"), leases)
        self.assertEqual(self.core.session_snapshot("session-2")["session_status"], "ended")

    def test_digital_end_does_not_allocate_physical_slot(self):
        self.start()
        holder = self.core.device_slot("edge-1")
        self.core.register_edge("digital-edge", "boot-1", ["conversation"], execution_class="digital")
        grant_id = self.second_session("digital-session", "digital-edge")
        self.core.issue_lease("digital-session", "ai-1", "ai-1", "conversation", grant_id)
        self.core.provision_session_end("digital-session", "ender")
        self.core.end_session("digital-session", "ender")
        self.assertEqual(self.core.active_leases("digital-session"), [])
        self.assertEqual(self.core.device_slot("digital-edge")["state"], "free")
        self.assertEqual(self.core.device_events("digital-edge"), [])
        self.assertEqual(self.core.device_slot("edge-1"), holder)

    def test_restart_quarantines_pending_fence_without_resurrecting_session(self):
        self.start()
        self.lease()
        self.core.provision_session_end("session-1", "ender")
        self.core.end_session("session-1", "ender")
        before = self.core.device_slot("edge-1")
        self.core.close()
        with RuntimeCore(self.path, trusted_clock=self.clock.wall) as restarted:
            slot = restarted.device_slot("edge-1")
            self.assertEqual(slot["state"], "quarantined")
            self.assertEqual(slot["device_epoch"], before["device_epoch"])
            self.assertEqual(slot["fence_correlation_id"], before["fence_correlation_id"])
            self.assertEqual(restarted.session_snapshot("session-1")["session_status"], "ended")
            self.assertEqual(restarted.active_leases("session-1"), [])
            self.assertReason("session_ended", restarted.activate_session, "session-1", "autonomous")
            restarted.end_session("session-1", "ender")

    def test_edge_boot_change_quarantines_pending_fence(self):
        self.start()
        self.lease()
        self.core.provision_session_end("session-1", "ender")
        self.core.end_session("session-1", "ender")
        self.core.register_edge("edge-1", "boot-2", ["conversation", "gesture"],
                                acquire_principal_id="device-admin")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "quarantined")
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ended")

    def test_end_rolls_back_if_device_audit_fails(self):
        self.start()
        self.lease()
        self.core.provision_session_end("session-1", "ender")
        before = (self.core.session_snapshot("session-1"), self.core.device_slot("edge-1"),
                  self.core.active_leases("session-1"), self.core.pending_edge_updates("edge-1"),
                  self.core.events("session-1"), self.core.device_events("edge-1"))
        with patch.object(self.core, "_device_audit", side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError, "audit failure"):
                self.core.end_session("session-1", "ender")
        self.assertEqual(before, (self.core.session_snapshot("session-1"), self.core.device_slot("edge-1"),
                                  self.core.active_leases("session-1"), self.core.pending_edge_updates("edge-1"),
                                  self.core.events("session-1"), self.core.device_events("edge-1")))

    def test_end_and_acquire_are_serialized(self):
        self.start(acquire_device=False)
        self.core.provision_session_end("session-1", "ender")
        gate = threading.Barrier(2)
        def acquire():
            gate.wait(timeout=5)
            try:
                self.core.acquire_device("session-1", "device-admin")
                return True
            except CoreDenied as error:
                self.assertEqual(error.reason, "session_ended")
                return False
        def end():
            gate.wait(timeout=5)
            self.core.end_session("session-1", "ender")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, e = pool.submit(acquire), pool.submit(end)
            acquired = a.result(timeout=10)
            e.result(timeout=10)
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ended")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "transferring" if acquired else "free")
        self.assertEqual(self.core.active_leases("session-1"), [])

    def test_acquire_only_slot_migration_preserves_retained_authority(self):
        self.start()
        before = self.core.device_slot("edge-1")
        self.core.close()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("ALTER TABLE device_slots RENAME TO lifecycle_slots")
            db.execute("""CREATE TABLE device_slots (
                edge_id TEXT PRIMARY KEY, state TEXT NOT NULL CHECK(state IN ('free','held','quarantined')),
                session_id TEXT, device_epoch INTEGER NOT NULL CHECK(device_epoch>=0),
                reason TEXT, updated_at TEXT NOT NULL)""")
            db.execute("INSERT INTO device_slots SELECT edge_id,state,session_id,device_epoch,reason,updated_at FROM lifecycle_slots")
            db.execute("DROP TABLE lifecycle_slots")
        with RuntimeCore(self.path, trusted_clock=self.clock.wall) as restarted:
            after = restarted.device_slot("edge-1")
            self.assertEqual((after["state"], after["session_id"], after["device_epoch"]),
                             ("quarantined", before["session_id"], before["device_epoch"]))
            self.assertIsNone(after["transfer_deadline"])
            self.assertReason("session_end_not_authorized", restarted.end_session, "session-1", "ender")

    def test_epoch_exhaustion_remains_nonfree(self):
        self.start()
        self.core.provision_session_end("session-1", "ender")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE device_slots SET device_epoch=? WHERE edge_id=?", (2**53-1, "edge-1"))
        self.core.end_session("session-1", "ender")
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["device_epoch"], slot["reason"]),
                         ("quarantined", 2**53-1, "device_epoch_exhausted"))
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ended")
