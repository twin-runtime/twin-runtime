"""Regression tests for the public Edge message contract and fencing rule."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from reference.edge_fence import EdgeFenceState

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "spec/v0.1/edge-authority.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def install(generation=11, sequence=1, lease="lease-b", controller="human-1", boot="boot-1", domain="conversation"):
    return dict(kind="edge.authority_install", edge_id="edge-1", edge_boot_id=boot,
                session_id="session-1", control_domain=domain, lease_id=lease,
                controller_id=controller, generation=generation,
                installation_sequence=sequence,
                lease_valid_until="2099-11-09T16:00:00Z", max_local_ttl_ms=1500)


def revoke(generation=12, sequence=1, boot="boot-1"):
    return dict(kind="edge.authority_revoke", edge_id="edge-1", edge_boot_id=boot,
                session_id="session-1", control_domain="conversation",
                generation=generation, installation_sequence=sequence,
                reason="representation_grant_revoked")


class TestSchema(unittest.TestCase):
    def test_draft_schema_valid(self):
        Draft202012Validator.check_schema(SCHEMA)

    def test_registration(self):
        msg = dict(kind="edge.register", edge_id="edge-1", edge_boot_id="boot-1",
                   supported_control_domains=["conversation", "gesture"])
        self.assertTrue(VALIDATOR.is_valid(msg))

    def test_install_and_revoke(self):
        self.assertTrue(VALIDATOR.is_valid(install()))
        self.assertTrue(VALIDATOR.is_valid(revoke()))

    def test_missing_epoch_is_invalid(self):
        msg = install()
        msg.pop("edge_boot_id")
        self.assertFalse(VALIDATOR.is_valid(msg))

    def test_non_positive_sequence_is_invalid(self):
        msg = install(sequence=0)
        self.assertFalse(VALIDATOR.is_valid(msg))

    def test_bool_generation_is_invalid(self):
        msg = install(generation=True)
        self.assertFalse(VALIDATOR.is_valid(msg))

    def test_expired_date_format_is_invalid(self):
        msg = install()
        msg["lease_valid_until"] = "yesterday"
        self.assertFalse(VALIDATOR.is_valid(msg))

    def test_unknown_field_is_invalid(self):
        msg = install()
        msg["unsafe_override"] = True
        self.assertFalse(VALIDATOR.is_valid(msg))


class TestEdgeFencing(unittest.TestCase):
    def setUp(self):
        self.edge = EdgeFenceState("edge-1", "boot-1", supported_control_domains=("conversation", "gesture"), trusted_wall_clock=lambda: datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc))

    def test_stale_installation_after_revocation_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        self.assertTrue(self.edge.accept_from_authenticated_core(revoke(12, 1)))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(11, 2)))
        self.assertEqual(self.edge.snapshot("session-1", "conversation").kind, "edge.authority_revoke")

    def test_delayed_same_generation_renewal_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 3)))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(11, 2)))

    def test_renewal_cannot_swap_controller(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(11, 2, controller="ai-1")))

    def test_revoked_generation_cannot_be_resurrected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        self.assertTrue(self.edge.accept_from_authenticated_core(revoke(12, 1)))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(12, 99)))
        self.assertTrue(self.edge.accept_from_authenticated_core(install(13, 1, lease="lease-c")))

    def test_duplicate_installation_rejected(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(11, 1)))

    def test_reboot_requires_new_epoch(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        new_edge = EdgeFenceState("edge-1", "boot-2", supported_control_domains=("conversation", "gesture"), trusted_wall_clock=lambda: datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc))
        self.assertFalse(new_edge.accept_from_authenticated_core(install(11, 1, boot="boot-1")))
        # Core is responsible for fencing previous epoch before issuing a fresh generation.
        self.assertTrue(new_edge.accept_from_authenticated_core(install(12, 1, lease="lease-c", boot="boot-2")))

    def test_two_domains_are_separate(self):
        self.assertTrue(self.edge.accept_from_authenticated_core(install(11, 1)))
        self.assertTrue(self.edge.accept_from_authenticated_core(install(3, 1, domain="gesture")))
        self.assertFalse(self.edge.accept_from_authenticated_core(install(10, 1)))
        self.assertIsNotNone(self.edge.snapshot("session-1", "gesture"))

    def test_wrong_edge_id_rejected(self):
        message = install()
        message["edge_id"] = "edge-intruder"
        self.assertFalse(self.edge.accept_from_authenticated_core(message))


if __name__ == "__main__":
    unittest.main()
