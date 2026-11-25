"""Reference release/admin intent tests; no physical safe-state confirmation."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

import test_runtime_core as runtime
import test_device_exclusivity as devices
from reference.runtime_core import CoreDenied, RuntimeCore


class TestDeviceRelease(unittest.TestCase):
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

    def provision(self):
        self.core.provision_device_operation("edge-1", "release", "releaser")
        self.core.provision_device_operation("edge-1", "admin_revoke", "revoker")

    def release(self, actor="releaser", sid="session-1", epoch=1):
        return self.core.release_device(sid, actor, expected_device_epoch=epoch)

    def admin(self, actor="revoker", why="maintenance", epoch=1):
        return self.core.admin_revoke("edge-1", actor, why, expected_device_epoch=epoch)

    def authority(self):
        return (self.core.device_slot("edge-1"), self.core.session_snapshot("session-1"),
                self.core.active_leases("session-1"), self.core.pending_edge_updates("edge-1"))

    def test_independent_roles_and_denials(self):
        self.start()
        self.lease()
        before = self.authority()
        self.assertReason("device_release_not_authorized", self.release, "device-admin")
        self.assertReason("device_admin_revoke_not_authorized", self.admin, "device-admin")
        self.provision()
        self.provision()
        self.assertReason("device_operation_principal_immutable", self.core.provision_device_operation,
                          "edge-1", "release", "other")
        for fn, actor, reason in ((self.release, "revoker", "device_release_not_authorized"),
                                   (self.admin, "releaser", "device_admin_revoke_not_authorized"),
                                   (self.release, "ai-1", "device_release_not_authorized"),
                                   (self.admin, "owner-controller", "device_admin_revoke_not_authorized"),
                                   (self.release, "", "principal_not_authenticated")):
            d = len(self.core.device_events("edge-1"))
            s = len(self.core.events("session-1"))
            self.assertReason(reason, fn, actor)
            de = self.core.device_events("edge-1")
            se = self.core.events("session-1")
            self.assertEqual((len(de), len(se)), (d+1, s+1))
            self.assertEqual((de[-1]["status"], de[-1]["reason"]), ("denied", reason))
            self.assertEqual(de[-1]["correlation_id"], se[-1]["correlation_id"])
            self.assertEqual(de[-1]["operation"], se[-1]["data"]["operation"])
            self.assertEqual(self.authority(), before)

    def test_nonholder_cannot_release_holder(self):
        self.start()
        self.second_session()
        self.lease()
        self.provision()
        before = self.authority()
        self.assertReason("device_busy", self.release, sid="session-2")
        self.assertEqual(self.authority(), before)
        event = self.core.device_events("edge-1")[-1]
        self.assertEqual((event["session_id"], event["prior_session_id"]), ("session-2", "session-1"))
        self.assertEqual(event["correlation_id"], self.core.events("session-2")[-1]["correlation_id"])

    def test_holder_release_fences_every_domain_and_keeps_pending(self):
        self.start("bridge")
        self.second_session()
        a = self.lease("ai-1", "conversation")
        b = self.lease("owner-controller", "gesture")
        self.pump()
        self.lease("owner-controller", "conversation")
        self.provision()
        slot = self.release()
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]),
                         ("transferring", "session-1", 2))
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "suspended")
        self.assertEqual(self.core.active_leases("session-1"), [])
        updates = self.core.pending_edge_updates("edge-1")
        self.assertTrue(updates)
        self.assertTrue(all(m["kind"] == "edge.authority_revoke" and m["device_epoch"] == 1 for _, m in updates))
        self.pump()
        self.assertFalse(self.edge.check_command(self.command(a), "ai-1")[0])
        self.assertFalse(self.edge.check_command(self.command(b), "owner-controller")[0])
        self.assertEqual(self.core.device_slot("edge-1"), slot)
        self.assertReason("device_transfer_pending", self.core.acquire_device, "session-2", "device-admin")
        self.assertReason("device_transfer_pending", self.core.activate_session, "session-1", "autonomous")
        events = self.core.device_events("edge-1")
        self.assertEqual([e["status"] for e in events], ["acquired", "release_requested", "fence_requested", "denied"])
        self.assertEqual(events[1]["correlation_id"], events[2]["correlation_id"])
        self.assertEqual(events[1]["actor_id"], "releaser")

    def test_repeat_matches_original_pending_request_only(self):
        self.start()
        self.provision()
        slot = self.release()
        events = self.core.device_events("edge-1")
        self.assertEqual(self.release(), slot)
        self.assertEqual(self.core.device_events("edge-1"), events)
        self.assertReason("device_transfer_pending", self.release, epoch=2)
        self.assertReason("device_transfer_pending", self.admin)
        self.assertEqual(self.core.device_slot("edge-1"), slot)

    def test_admin_revoke_preserves_reason_and_own_idempotency(self):
        self.start()
        self.lease()
        self.second_session()
        self.provision()
        slot = self.admin()
        self.assertEqual((slot["state"], slot["reason"], slot["device_epoch"]),
                         ("transferring", "admin_revoke:maintenance", 2))
        self.assertEqual(self.core.active_leases("session-1"), [])
        self.assertEqual(self.admin(), slot)
        self.assertReason("device_transfer_pending", self.admin, why="another")
        self.assertReason("device_transfer_pending", self.release)
        self.assertReason("device_transfer_pending", self.core.acquire_device, "session-2", "device-admin")
        event = next(e for e in self.core.device_events("edge-1") if e["status"] == "fence_requested")
        self.assertEqual((event["actor_class"], event["actor_id"]), ("admin_revoke_principal", "revoker"))

    def test_expected_epoch_and_reason_validation(self):
        self.start()
        self.provision()
        before = self.authority()
        for epoch in (0, -1, True, "1", 2**53):
            self.assertReason("invalid_expected_device_epoch", self.release, epoch=epoch)
        self.assertReason("device_epoch_conflict", self.admin, epoch=2)
        self.assertReason("invalid_device_operation_reason", self.admin, why="a"*129)
        self.assertReason("invalid_device_operation_reason", self.admin, why="bad\x00reason")
        self.assertEqual(self.authority(), before)

    def test_actor_ids_bounded_in_end_and_device_denials(self):
        self.start()
        self.provision()
        self.core.provision_session_end("session-1", "ender")
        before = self.authority()
        for actor in ("x"*129, "bad\x00id", "invalid name"):
            self.assertReason("principal_not_authenticated", self.release, actor)
            self.assertNotIn("actor_id", self.core.device_events("edge-1")[-1])
            self.assertNotIn("actor_id", self.core.events("session-1")[-1]["data"])
            self.assertReason("principal_not_authenticated", self.core.end_session, "session-1", actor)
            self.assertNotIn("actor_id", self.core.device_events("edge-1")[-1])
            self.assertNotIn("actor_id", self.core.events("session-1")[-1]["data"])
        self.assertEqual(self.authority(), before)

    def test_transfer_deadline_quarantines_without_changing_epoch(self):
        self.start()
        self.second_session()
        self.provision()
        slot = self.release()
        self.clock.advance(29)
        self.assertEqual(self.core.process_transfer_deadlines(), 0)
        self.clock.advance(1)
        self.assertReason("device_state_unverified", self.release)
        self.assertReason("device_transfer_pending", self.core.acquire_device, "session-2", "device-admin")
        self.assertEqual(self.core.process_transfer_deadlines(), 1)
        after = self.core.device_slot("edge-1")
        self.assertEqual((after["state"], after["reason"]), ("quarantined", "transfer_deadline_elapsed"))
        self.assertEqual(after["device_epoch"], slot["device_epoch"])
        for key in ("fence_boot_id", "fence_correlation_id", "session_id", "transfer_deadline"):
            self.assertEqual(after[key], slot[key])
        self.assertEqual(self.core.device_events("edge-1")[-1]["correlation_id"], slot["fence_correlation_id"])
        self.assertEqual(self.core.events("session-1")[-1]["correlation_id"], slot["fence_correlation_id"])
        self.assertEqual(self.core.process_transfer_deadlines(), 0)
        self.assertReason("device_state_unverified", self.core.acquire_device, "session-2", "device-admin")

    def test_end_session_deadline_uses_same_processing(self):
        self.start()
        self.core.provision_session_end("session-1", "ender")
        self.core.end_session("session-1", "ender")
        self.clock.advance(30)
        self.assertEqual(self.core.process_transfer_deadlines(), 1)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "quarantined")
        self.assertEqual(self.core.session_snapshot("session-1")["session_status"], "ended")

    def test_restart_preserves_pending_authority_and_role_bindings(self):
        self.start()
        self.provision()
        before = self.admin()
        self.core.close()
        with RuntimeCore(self.path, trusted_clock=self.clock.wall) as core:
            after = core.device_slot("edge-1")
            self.assertEqual(after["state"], "quarantined")
            self.assertEqual(after["device_epoch"], before["device_epoch"])
            self.assertEqual(after["fence_correlation_id"], before["fence_correlation_id"])
            self.assertReason("device_operation_principal_immutable", core.provision_device_operation,
                              "edge-1", "admin_revoke", "other")
            self.assertReason("device_state_unverified", core.admin_revoke, "edge-1", "revoker", "maintenance", expected_device_epoch=1)
            self.assertEqual(core.process_transfer_deadlines(), 0)

    def test_release_and_deadline_audit_failure_rollback(self):
        self.start()
        self.lease()
        self.provision()
        before = self.authority()
        events = self.core.events("session-1"), self.core.device_events("edge-1")
        with patch.object(self.core, "_device_audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaisesRegex(RuntimeError, "audit failed"):
                self.release()
        self.assertEqual(self.authority(), before)
        self.assertEqual((self.core.events("session-1"), self.core.device_events("edge-1")), events)
        slot = self.release()
        self.clock.advance(30)
        with patch.object(self.core, "_audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaisesRegex(RuntimeError, "audit failed"):
                self.core.process_transfer_deadlines()
        self.assertEqual(self.core.device_slot("edge-1"), slot)
        self.assertEqual(self.core.process_transfer_deadlines(), 1)

    def test_release_admin_and_successor_race_never_frees(self):
        self.start()
        self.lease()
        self.second_session()
        self.provision()
        gate = threading.Barrier(3)
        def run(fn):
            gate.wait(timeout=5)
            try:
                return fn()["state"]
            except CoreDenied as e:
                return e.reason
        with ThreadPoolExecutor(max_workers=3) as pool:
            fs = [pool.submit(run, fn) for fn in (self.release, self.admin,
                lambda: self.core.acquire_device("session-2", "device-admin"))]
            results = [f.result(timeout=10) for f in fs]
        self.assertEqual(results.count("transferring"), 1)
        self.assertEqual(results.count("device_transfer_pending") + results.count("device_busy"), 2)
        slot = self.core.device_slot("edge-1")
        self.assertEqual((slot["state"], slot["session_id"], slot["device_epoch"]), ("transferring", "session-1", 2))
        self.assertEqual(self.core.active_leases("session-1"), [])
        events = self.core.device_events("edge-1")
        self.assertEqual(sum(e["status"] == "fence_requested" for e in events), 1)
        self.assertEqual([e["device_sequence"] for e in events], list(range(1, len(events)+1)))

    def test_digital_and_free_slots_do_not_create_authority(self):
        self.provision()
        self.assertReason("device_not_acquired", self.release)
        self.assertReason("device_not_acquired", self.admin)
        self.assertEqual(self.core.device_slot("edge-1")["state"], "free")
        self.assertEqual(self.core.device_events("edge-1")[-1]["operation"], "admin_revoke")
        self.core.register_edge("digital-edge", "boot-1", ["conversation"], execution_class="digital")
        self.assertReason("device_slot_not_required", self.core.provision_device_operation,
                          "digital-edge", "release", "releaser")
        self.assertEqual(self.core.device_slot("digital-edge")["state"], "free")
