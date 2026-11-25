"""C-1B hold, Grant-loss and trusted-clock lifecycle tests (software reference only)."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
import threading
import unittest
from unittest.mock import patch

import test_runtime_core as runtime
import test_device_exclusivity as devices
from reference.runtime_core import CoreDenied, RuntimeCore


class TestDeviceLifecycleDeadlines(unittest.TestCase):
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

    def hold(self, edge_id="edge-1"):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT session_id,device_epoch,deadline,correlation_id "
                              "FROM device_hold_deadlines WHERE edge_id=?", (edge_id,)).fetchone()

    def test_hold_timeout_configuration_is_finite(self):
        for invalid in (0, -1, 3601, True, None):
            self.assertReason("invalid_slot_hold_timeout", RuntimeCore, self.path,
                              trusted_clock=self.clock.wall, slot_hold_timeout_seconds=invalid)

    def test_hold_timeout_is_finite_and_not_extended_by_repeat(self):
        self.start("bridge")
        self.lease("owner-controller")
        self.core.owner_disconnected("session-1")
        original = self.hold()
        self.assertEqual(original[:2], ("session-1", 1))
        self.clock.advance(59)
        self.core.revoke_session_control("session-1")
        self.assertEqual(self.hold(), original)
        self.assertEqual(self.core.process_lifecycle_deadlines(), 0)
        self.clock.advance(1)
        self.assertEqual(self.core.process_lifecycle_deadlines(), 1)
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["reason"], slot["device_epoch"]),
                         ("transferring", "slot_hold_timeout", 2))
        self.assertEqual(slot["fence_correlation_id"], original[3])
        self.assertIsNone(self.hold())
        self.assertEqual(self.core.active_leases("session-1"), [])
        self.assertTrue(all(m["kind"] != "edge.authority_install" for _, m in self.core.pending_edge_updates("edge-1")))
        self.assertEqual(self.core.process_lifecycle_deadlines(), 0)
        self.clock.advance(30)
        self.assertEqual(self.core.process_lifecycle_deadlines(), 1)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "quarantined")

    def test_resume_before_deadline_cancels_hold_but_late_resume_fences(self):
        self.start("bridge")
        self.core.owner_disconnected("session-1")
        before = self.hold()
        self.clock.advance(59)
        self.core.activate_session("session-1", "bridge", owner_presence_confirmed=True)
        self.assertIsNone(self.hold())
        self.core.owner_disconnected("session-1")
        self.assertNotEqual(self.hold()[2], before[2])
        self.clock.advance(60)
        self.assertReason("device_transfer_pending", self.core.activate_session,
                          "session-1", "bridge", owner_presence_confirmed=True)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "transferring")

    def test_expired_hold_cannot_be_bypassed_by_successor_acquire(self):
        self.start("bridge")
        self.second_session()
        self.core.owner_disconnected("session-1")
        self.clock.advance(60)
        self.assertReason("device_transfer_pending", self.core.acquire_device, "session-2", "device-admin")
        self.assertEqual(self.core.device_slot("edge-1")["session_id"], "session-1")
        self.assertEqual(self.core.device_slot("edge-1")["device_epoch"], 2)

    def test_nonholder_suspension_does_not_arm_holder_deadline(self):
        self.start()
        self.second_session()
        self.core.revoke_session_control("session-2")
        self.assertIsNone(self.hold())
        self.clock.advance(60)
        self.assertEqual(self.core.process_lifecycle_deadlines(), 0)
        self.assertEqual(self.core.device_slot("edge-1")["session_id"], "session-1")

    def test_ready_holder_loses_last_grant_immediately(self):
        self.core.acquire_device("session-1", "device-admin")
        self.core.revoke_grant("grant-1")
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "suspended")
        self.assertEqual(self.core.device_slot("edge-1")["reason"], "all_supporting_grants_lost")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "transferring")

    def test_partial_grant_revocation_does_not_fence(self):
        self.core.provision_grant(self.grant(grant_id="grant-2"))
        self.core.create_session("multi", "owner-1", "twin-1", ["grant-1", "grant-2"], "edge-1")
        self.core.set_policies("multi", self.policy(policy_id="multi-policy", session_id="multi"),
                               self.compliance(policy_id="multi-compliance", session_id="multi"))
        self.core.prepare_session("multi")
        self.core.activate_session("multi", "autonomous")
        self.core.acquire_device("multi", "device-admin")
        self.core.issue_lease("multi", "ai-1", "ai-1", "conversation", "grant-1")
        self.core.revoke_grant("grant-1")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "held")
        self.assertEqual(self.core.active_leases("multi"), [])
        self.core.issue_lease("multi", "ai-1", "ai-1", "gesture", "grant-2")
        self.core.revoke_grant("grant-2")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "transferring")
        self.assertEqual(self.core.active_leases("multi"), [])

    def test_expired_grant_fences_before_install_delivery(self):
        self.start()
        self.lease()
        self.clock.advance(30*60)
        updates = self.core.pending_edge_updates("edge-1")
        self.assertTrue(updates)
        self.assertTrue(all(m["kind"] == "edge.authority_revoke" for _, m in updates))
        self.assertEqual(self.core.device_slot("edge-1")["reason"], "all_supporting_grants_lost")
        self.assertEqual(self.core.active_leases("session-1"), [])

    def test_digital_grant_loss_does_not_create_physical_fence(self):
        self.core.register_edge("digital-edge", "boot-1", ["conversation"], execution_class="digital")
        gid = self.second_session("digital-session", "digital-edge")
        self.core.revoke_grant(gid)
        self.assertEqual(self.core.device_slot("digital-edge")["state"], "free")
        self.assertIsNone(self.hold("digital-edge"))
        self.assertEqual(self.core.device_events("digital-edge"), [])

    def test_hold_timeout_audit_failure_rolls_back(self):
        self.start("bridge")
        self.core.owner_disconnected("session-1")
        before = self.core.device_slot("edge-1"), self.hold(), self.core.events("session-1")
        self.clock.advance(60)
        with patch.object(self.core, "_device_audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaisesRegex(RuntimeError, "audit failed"):
                self.core.process_lifecycle_deadlines()
        self.assertEqual((self.core.device_slot("edge-1"), self.hold(), self.core.events("session-1")), before)
        self.assertEqual(self.core.process_lifecycle_deadlines(), 1)

    def test_clock_rollback_quarantines_held_and_pending_slots(self):
        self.start()
        self.lease()
        self.core.register_edge("edge-2", "boot-1", ["conversation"], acquire_principal_id="device-admin")
        self.second_session("session-2", "edge-2")
        self.core.acquire_device("session-2", "device-admin")
        self.core.provision_session_end("session-2", "ender")
        self.core.end_session("session-2", "ender")
        pending = self.core.device_slot("edge-2")
        self.clock.advance(10)
        self.assertEqual(self.core.process_lifecycle_deadlines(), 0)
        self.clock.advance(-1)
        self.assertReason("clock_untrusted", self.core.process_lifecycle_deadlines)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "quarantined")
        after = self.core.device_slot("edge-2")
        self.assertEqual(after["state"], "quarantined")
        self.assertEqual(after["fence_correlation_id"], pending["fence_correlation_id"])
        self.assertEqual(after["device_epoch"], pending["device_epoch"])
        self.assertEqual(self.core.active_leases("session-1"), [])
        self.assertTrue(all(m["kind"] == "edge.authority_revoke" for _, m in self.core.pending_edge_updates("edge-1")))
        count = len(self.core.device_events("edge-1"))
        self.assertReason("clock_untrusted", self.core.process_lifecycle_deadlines)
        self.assertEqual(len(self.core.device_events("edge-1")), count)
        self.clock.advance(1)
        self.assertReason("device_state_unverified", self.lease)

    def test_invalid_clock_quarantines_before_denial_and_allows_revokes(self):
        self.start()
        self.lease()
        with patch.object(self.core, "_clock", return_value=None):
            self.assertReason("clock_untrusted", self.core.process_lifecycle_deadlines)
            self.assertEqual(self.core.device_slot("edge-1")["reason"], "clock_untrusted")
            updates = self.core.pending_edge_updates("edge-1")
            self.assertTrue(updates)
            self.assertTrue(all(m["kind"] == "edge.authority_revoke" for _, m in updates))
            self.core.acknowledge_edge_update(updates[0][0], "edge-1")
        self.assertEqual(self.core.device_slot("edge-1")["state"], "quarantined")

    def test_watermark_survives_denied_request_and_restart(self):
        self.start()
        self.clock.advance(10)
        self.assertReason("unknown_session", self.core.end_session, "missing", "ender")
        self.core.close()
        self.clock.advance(-1)
        with RuntimeCore(self.path, trusted_clock=self.clock.wall) as restarted:
            self.assertEqual(restarted.device_slot("edge-1")["reason"], "clock_untrusted")
            self.assertReason("clock_untrusted", restarted.process_lifecycle_deadlines)
            self.clock.advance(1)
            self.assertReason("device_state_unverified", restarted.acquire_device, "session-1", "device-admin")

    def test_hold_deadline_and_resume_race_is_fail_closed(self):
        self.start("bridge")
        self.core.owner_disconnected("session-1")
        self.clock.advance(60)
        gate = threading.Barrier(2)
        def resume():
            gate.wait(timeout=5)
            self.assertReason("device_transfer_pending", self.core.activate_session,
                              "session-1", "bridge", owner_presence_confirmed=True)
        def tick():
            gate.wait(timeout=5)
            return self.core.process_lifecycle_deadlines()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(resume), pool.submit(tick)
            a.result(timeout=10)
            self.assertIn(b.result(timeout=10), (0, 1))
        events = self.core.device_events("edge-1")
        self.assertEqual(sum(e["status"] == "fence_requested" for e in events), 1)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "transferring")
