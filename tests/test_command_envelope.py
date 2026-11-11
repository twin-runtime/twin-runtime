"""CommandEnvelope and Edge authority checks. This is not OEM safety testing."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from reference.edge_fence import EdgeFenceState

ROOT = Path(__file__).resolve().parents[1]
COMMAND_SCHEMA = json.loads((ROOT / "spec/v0.1/command-envelope.schema.json").read_text())
EDGE_SCHEMA = json.loads((ROOT / "spec/v0.1/edge-authority.schema.json").read_text())
COMMAND_VALIDATOR = Draft202012Validator(COMMAND_SCHEMA, format_checker=FormatChecker())
EDGE_VALIDATOR = Draft202012Validator(EDGE_SCHEMA, format_checker=FormatChecker())


class FakeClock:
    def __init__(self):
        self.mono = 100.0
        self.wall = datetime(2026, 11, 9, 15, tzinfo=timezone.utc)

    def monotonic(self):
        return self.mono

    def utc(self):
        return self.wall

    def advance(self, seconds: float, wall=True):
        self.mono += seconds
        if wall:
            self.wall += timedelta(seconds=seconds)


def install(gen=11, seq=1, lease="lease-b", controller="human-1", domain="conversation", ttl=1500, boot="boot-1", until="2026-11-09T15:10:00Z"):
    return dict(kind="edge.authority_install", edge_id="edge-1", edge_boot_id=boot,
                session_id="session-1", control_domain=domain, generation=gen,
                installation_sequence=seq, lease_id=lease, controller_id=controller,
                lease_valid_until=until, max_local_ttl_ms=ttl)


def revoke(gen=12, seq=1):
    return dict(kind="edge.authority_revoke", edge_id="edge-1", edge_boot_id="boot-1",
                session_id="session-1", control_domain="conversation", generation=gen,
                installation_sequence=seq, reason="policy_changed")


def command(gen=11, lease="lease-b", controller="human-1", domain="conversation", cid="cmd-1"):
    return dict(command_id=cid, session_id="session-1", controller_id=controller,
                control_domain=domain, lease_id=lease, lease_generation=gen,
                issued_at="2026-11-09T15:00:00Z", payload={"say": "hello"})


class TestCommandSchema(unittest.TestCase):
    def test_valid_schema(self):
        Draft202012Validator.check_schema(COMMAND_SCHEMA)
        Draft202012Validator.check_schema(EDGE_SCHEMA)

    def test_valid_inline_payload(self):
        self.assertTrue(COMMAND_VALIDATOR.is_valid(command()))

    def test_valid_payload_reference(self):
        c = command()
        c.pop("payload")
        c["payload_reference"] = "urn:payload:1"
        self.assertTrue(COMMAND_VALIDATOR.is_valid(c))

    def test_missing_command_id(self):
        c = command()
        c.pop("command_id")
        self.assertFalse(COMMAND_VALIDATOR.is_valid(c))

    def test_both_payloads_rejected(self):
        c = command()
        c["payload_reference"] = "urn:payload:1"
        self.assertFalse(COMMAND_VALIDATOR.is_valid(c))

    def test_missing_payload_rejected(self):
        c = command()
        c.pop("payload")
        self.assertFalse(COMMAND_VALIDATOR.is_valid(c))

    def test_generation_true_rejected(self):
        c = command(gen=True)
        self.assertFalse(COMMAND_VALIDATOR.is_valid(c))

    def test_generation_too_big_rejected(self):
        c = command(gen=2**53)
        self.assertFalse(COMMAND_VALIDATOR.is_valid(c))
        self.assertFalse(EDGE_VALIDATOR.is_valid(install(gen=2**53)))

    def test_command_id_max_length(self):
        self.assertFalse(COMMAND_VALIDATOR.is_valid(command(cid="a" * 129)))

    def test_unknown_fields_rejected(self):
        c = command()
        c["bypass_auth"] = True
        self.assertFalse(COMMAND_VALIDATOR.is_valid(c))


class TestCommandAuthorization(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.edge = EdgeFenceState("edge-1", "boot-1",
                                   supported_control_domains=("conversation", "gesture"),
                                   monotonic_clock=self.clock.monotonic,
                                   trusted_wall_clock=self.clock.utc)

    def test_authorized_command_accepted(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        self.assertEqual(self.edge.check_command(command(), "human-1"), (True, "accepted"))

    def test_authenticated_sender_mismatch_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        self.assertEqual(self.edge.check_command(command(), "ai-1"), (False, "controller_mismatch"))

    def test_old_generation_after_handover_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        self.assertTrue(self.edge.accept_from_authenticated_core(install(gen=12, lease="lease-c", controller="ai-1")))
        self.assertEqual(self.edge.check_command(command(), "human-1"), (False, "stale_generation"))
        self.assertEqual(self.edge.check_command(command(gen=12, lease="lease-c", controller="ai-1"), "ai-1"), (True, "accepted"))

    def test_command_after_revoke_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        self.assertTrue(self.edge.accept_from_authenticated_core(revoke()))
        self.assertEqual(self.edge.check_command(command(), "human-1"), (False, "revoked"))

    def test_expired_by_monotonic_deadline_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(ttl=1500)))
        self.clock.advance(1.6, wall=False)
        self.assertEqual(self.edge.check_command(command(), "human-1"), (False, "expired"))

    def test_install_cannot_extend_past_lease_valid_until(self):
        i = install(ttl=5000, until="2026-11-09T15:00:00.800Z")
        self.assertTrue(self.edge.accept_from_authenticated_core(i))
        self.clock.advance(.9, wall=False)
        self.assertEqual(self.edge.check_command(command(), "human-1"), (False, "expired"))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(gen=11, seq=2, ttl=99999, until="2026-11-09T14:00:00Z")))

    def test_expired_generation_cannot_be_revived_by_renewal(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(ttl=1000)))
        self.clock.advance(1.1)
        self.assertEqual(self.edge.install_authority(install(seq=2, ttl=1500)), (False, "expired"))
        self.assertTrue(self.edge.accept_from_authenticated_core(install(gen=12, lease="lease-c")))

    def test_duplicate_command_id_rejected_across_renewal(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        self.assertEqual(self.edge.check_command(command(), "human-1"), (True, "accepted"))
        self.assertTrue(self.edge.accept_from_authenticated_core(install(seq=2)))
        self.assertEqual(self.edge.check_command(command(), "human-1"), (False, "duplicate_command"))

    def test_old_boot_command_rejected_after_restart(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        edge2 = EdgeFenceState("edge-1", "boot-2", supported_control_domains=("conversation",),
                               monotonic_clock=self.clock.monotonic, trusted_wall_clock=self.clock.utc)
        self.assertEqual(edge2.check_command(command(), "human-1"), (False, "no_authority"))
        self.assertTrue(edge2.accept_from_authenticated_core(install(gen=12, lease="lease-c", boot="boot-2")))
        self.assertEqual(edge2.check_command(command(), "human-1"), (False, "stale_generation"))

    def test_undeclared_domain_rejected(self):
        self.assertEqual(self.edge.install_authority(install(domain="navigation")), (False, "domain_unsupported"))
        self.assertEqual(self.edge.check_command(command(domain="navigation"), "human-1"), (False, "domain_unsupported"))

    def test_concurrent_install_cannot_overwrite_revocation(self):
        # Either order is allowed, but revocation generation 13 must prevail.
        for _ in range(40):
            edge = EdgeFenceState("edge-1", "boot-1", supported_control_domains=("conversation",),
                                  monotonic_clock=self.clock.monotonic, trusted_wall_clock=self.clock.utc)
            self.assertTrue(edge.accept_from_authenticated_core(install(gen=11)))
            barrier = threading.Barrier(3)

            def do_install():
                barrier.wait()
                return edge.accept_from_authenticated_core(install(gen=12, lease="lease-c"))

            def do_revoke():
                barrier.wait()
                return edge.accept_from_authenticated_core(revoke(gen=13))

            with ThreadPoolExecutor(max_workers=2) as pool:
                a, b = pool.submit(do_install), pool.submit(do_revoke)
                barrier.wait()
                a.result(timeout=2)
                b.result(timeout=2)
            self.assertEqual(edge.snapshot("session-1", "conversation").generation, 13)
            self.assertEqual(edge.snapshot("session-1", "conversation").kind, "edge.authority_revoke")

    def test_expired_install_rejected(self):
        self.assertEqual(self.edge.install_authority(install(until="2000-01-01T00:00:00Z")), (False, "expired"))

    def test_clock_untrusted_fails_closed(self):
        edge = EdgeFenceState("edge-1", "boot-1", supported_control_domains=("conversation",))
        self.assertEqual(edge.install_authority(install()), (False, "clock_untrusted"))

    def test_install_requires_first_sequence_one(self):
        self.assertEqual(self.edge.install_authority(install(seq=99)), (False, "stale_installation"))

    def test_same_lease_cannot_be_reused_at_next_generation(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(gen=11)))
        self.assertEqual(self.edge.install_authority(install(gen=12, lease="lease-b")), (False, "lease_reused"))

    def test_failed_command_does_not_consume_id(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        self.assertFalse(self.edge.check_command(command(), "ai-1")[0])
        self.assertTrue(self.edge.check_command(command(), "human-1")[0])

    def test_invalid_payload_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install()))
        c = command()
        c["payload_reference"] = "uri"
        self.assertEqual(self.edge.check_command(c, "human-1"), (False, "malformed"))


if __name__ == "__main__":
    unittest.main()
