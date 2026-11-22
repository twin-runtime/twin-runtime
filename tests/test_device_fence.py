"""Acquire-only device fencing in the simulated Edge, without hardware claims."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
import unittest

from reference.edge_fence import EdgeFenceState


def edge(*, execution_class="physical", boot="boot-1"):
    return EdgeFenceState(
        "edge-1", boot, execution_class=execution_class,
        supported_control_domains=("conversation", "gesture"),
        monotonic_clock=lambda: 100.0,
        trusted_wall_clock=lambda: datetime(2026, 11, 22, 12, tzinfo=timezone.utc),
    )


def install(*, epoch=7, session="session-a", domain="conversation",
            controller="ai-1", generation=1, boot="boot-1"):
    message = {
        "kind": "edge.authority_install", "edge_id": "edge-1", "edge_boot_id": boot,
        "session_id": session, "control_domain": domain,
        "generation": generation, "installation_sequence": 1,
        "lease_id": f"lease-{session}-{domain}-{generation}",
        "controller_id": controller, "lease_valid_until": "2026-11-22T12:01:00Z",
        "max_local_ttl_ms": 1500,
    }
    if epoch is not None:
        message["device_epoch"] = epoch
    return message


def revoke(*, epoch=7, session="session-a", generation=2):
    message = {
        "kind": "edge.authority_revoke", "edge_id": "edge-1", "edge_boot_id": "boot-1",
        "session_id": session, "control_domain": "conversation", "generation": generation,
        "installation_sequence": 1, "reason": "policy_changed",
    }
    if epoch is not None:
        message["device_epoch"] = epoch
    return message


def command(*, session="session-a", domain="conversation", controller="ai-1",
            generation=1, command_id="command-1"):
    return {
        "command_id": command_id, "session_id": session, "controller_id": controller,
        "control_domain": domain, "lease_id": f"lease-{session}-{domain}-{generation}",
        "lease_generation": generation, "issued_at": "2026-11-22T12:00:00Z",
        "payload": {"action": "simulated"},
    }


class TestDeviceFence(unittest.TestCase):
    def test_physical_edge_rejects_install_without_epoch(self):
        physical = EdgeFenceState(
            "edge-1", "boot-1", supported_control_domains=("conversation",),
            trusted_wall_clock=lambda: datetime(2026, 11, 22, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(physical.execution_class, "physical")
        self.assertEqual(physical.install_authority(install(epoch=None)),
                         (False, "device_state_unverified"))
        self.assertIsNone(physical.device_snapshot())

    def test_unknown_execution_class_treated_as_physical(self):
        for classification in (None, "", "unknown", "Digital", True):
            with self.subTest(classification=classification):
                physical = edge(execution_class=classification)
                self.assertEqual(physical.execution_class, "physical")
                self.assertEqual(physical.install_authority(install(epoch=None)),
                                 (False, "device_state_unverified"))

    def test_equal_epoch_other_session_conflict(self):
        physical = edge()
        self.assertEqual(physical.install_authority(install()), (True, "accepted"))
        for domain in ("conversation", "gesture"):
            with self.subTest(domain=domain):
                self.assertEqual(physical.install_authority(install(session="session-b", domain=domain)),
                                 (False, "device_epoch_conflict"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))

    def test_lower_epoch_stale(self):
        physical = edge()
        self.assertTrue(physical.install_authority(install())[0])
        self.assertEqual(physical.install_authority(install(epoch=6, session="session-b")),
                         (False, "device_epoch_stale"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))

    def test_higher_epoch_transfer_pending(self):
        physical = edge()
        self.assertTrue(physical.install_authority(install())[0])
        for session in ("session-a", "session-b"):
            with self.subTest(session=session):
                self.assertEqual(physical.install_authority(install(epoch=8, session=session)),
                                 (False, "device_transfer_pending"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))
        self.assertEqual(physical.check_command(command(), "ai-1"), (True, "accepted"))

    def test_revoke_wrong_epoch_rejected(self):
        physical = edge()
        self.assertTrue(physical.install_authority(install())[0])
        attempts = [
            (revoke(epoch=None), "device_state_unverified"),
            (revoke(epoch=6), "device_epoch_stale"),
            (revoke(session="session-b"), "device_epoch_conflict"),
            (revoke(epoch=8), "device_transfer_pending"),
        ]
        for message, reason in attempts:
            with self.subTest(reason=reason):
                self.assertEqual(physical.install_authority(message), (False, reason))
                self.assertEqual(physical.check_command(command(command_id=reason), "ai-1"),
                                 (True, "accepted"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))

    def test_cross_session_command_rejected(self):
        physical = edge()
        self.assertTrue(physical.install_authority(install())[0])
        forged = command(session="session-b")
        forged["lease_id"] = install()["lease_id"]
        self.assertEqual(physical.check_command(forged, "ai-1"), (False, "no_authority"))
        self.assertEqual(physical.check_command(command(), "ai-1"), (True, "accepted"))
        self.assertEqual(physical.snapshot("session-a", "conversation").device_epoch, 7)

    def test_new_boot_has_no_device_watermark(self):
        previous = edge()
        self.assertTrue(previous.install_authority(install())[0])
        restarted = edge(boot="boot-2")
        self.assertIsNone(restarted.device_snapshot())
        self.assertEqual(restarted.check_command(command(), "ai-1"), (False, "no_authority"))
        self.assertEqual(restarted.install_authority(install()), (False, "wrong_edge_epoch"))
        self.assertIsNone(restarted.device_snapshot())
        # Core must supply authenticated, reconciled authority for the new boot.
        self.assertEqual(restarted.install_authority(install(epoch=8, boot="boot-2")),
                         (True, "accepted"))
        self.assertEqual(restarted.device_snapshot(), (8, "session-a"))

    def test_digital_edge_unchanged(self):
        digital = edge(execution_class="digital")
        for session in ("session-a", "session-b"):
            self.assertEqual(digital.install_authority(install(epoch=None, session=session)),
                             (True, "accepted"))
            self.assertEqual(digital.check_command(command(session=session), "ai-1"),
                             (True, "accepted"))
        self.assertIsNone(digital.device_snapshot())
        self.assertEqual(digital.install_authority(revoke(epoch=None)), (True, "accepted"))
        self.assertEqual(digital.check_command(command(), "ai-1"), (False, "revoked"))
        self.assertEqual(digital.check_command(command(session="session-b", command_id="command-2"), "ai-1"),
                         (True, "accepted"))

    def test_bridge_two_controllers_same_session(self):
        physical = edge()
        self.assertEqual(physical.install_authority(install()), (True, "accepted"))
        self.assertEqual(physical.install_authority(install(domain="gesture", controller="owner-1")),
                         (True, "accepted"))
        self.assertEqual(physical.check_command(command(), "ai-1"), (True, "accepted"))
        self.assertEqual(physical.check_command(command(domain="gesture", controller="owner-1"), "owner-1"),
                         (True, "accepted"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))

    def test_failed_first_install_does_not_claim_device(self):
        attempts = [
            ({"lease_valid_until": "2000-01-01T00:00:00Z"}, "expired"),
            ({"edge_boot_id": "old-boot"}, "wrong_edge_epoch"),
            ({"installation_sequence": 2}, "stale_installation"),
            ({"control_domain": "navigation"}, "domain_unsupported"),
            ({"generation": 0}, "malformed"),
        ]
        for change, reason in attempts:
            with self.subTest(reason=reason):
                physical = edge()
                self.assertEqual(physical.install_authority({**install(), **change}), (False, reason))
                self.assertIsNone(physical.device_snapshot())
                self.assertEqual(physical.install_authority(install(session="session-b")), (True, "accepted"))
                self.assertEqual(physical.device_snapshot(), (7, "session-b"))

    def test_first_revoke_fences_without_installing_command_authority(self):
        physical = edge()
        self.assertEqual(physical.install_authority(revoke()), (True, "accepted"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))
        self.assertEqual(physical.check_command(command(), "ai-1"), (False, "revoked"))
        self.assertEqual(physical.install_authority(install()), (False, "stale_generation"))
        self.assertEqual(physical.install_authority(install(session="session-b")),
                         (False, "device_epoch_conflict"))
        self.assertEqual(physical.install_authority(install(generation=3)), (True, "accepted"))
        self.assertEqual(physical.check_command(command(generation=3), "ai-1"), (True, "accepted"))

    def test_revocation_does_not_release_device(self):
        physical = edge()
        self.assertTrue(physical.install_authority(install())[0])
        self.assertEqual(physical.install_authority(revoke()), (True, "accepted"))
        self.assertEqual(physical.install_authority(install(session="session-b", domain="gesture")),
                         (False, "device_epoch_conflict"))
        self.assertEqual(physical.install_authority(install(epoch=8, session="session-b")),
                         (False, "device_transfer_pending"))
        self.assertEqual(physical.device_snapshot(), (7, "session-a"))

    def test_concurrent_sessions_cannot_both_install(self):
        physical = edge()
        barrier = threading.Barrier(3)

        def attempt(session, domain):
            barrier.wait(timeout=5)
            return session, domain, physical.install_authority(install(session=session, domain=domain))

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt, "session-a", "conversation")
            second = pool.submit(attempt, "session-b", "gesture")
            barrier.wait(timeout=5)
            results = [first.result(timeout=5), second.result(timeout=5)]
        self.assertEqual(sorted(result for _, _, result in results),
                         [(False, "device_epoch_conflict"), (True, "accepted")])
        for session, domain, (accepted, _) in results:
            expected = (True, "accepted") if accepted else (False, "no_authority")
            self.assertEqual(physical.check_command(command(session=session, domain=domain), "ai-1"), expected)
            if accepted:
                self.assertEqual(physical.device_snapshot(), (7, session))

    def test_invalid_epoch_does_not_claim_device(self):
        for invalid in (True, 0, -1, 2**53, "7", None):
            with self.subTest(epoch=invalid):
                physical = edge()
                message = {**install(), "device_epoch": invalid}
                self.assertEqual(physical.install_authority(message), (False, "malformed"))
                self.assertIsNone(physical.device_snapshot())
                self.assertEqual(physical.install_authority(install(epoch=2**53 - 1)), (True, "accepted"))


if __name__ == "__main__":
    unittest.main()
