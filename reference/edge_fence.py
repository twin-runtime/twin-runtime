"""Reference-only authority fencing and command checks for one Edge boot.

Not production robot safety. The host MUST authenticate Core messages and
controller transports before calling this class. The host MUST establish a
trusted UTC clock, supply a fresh authenticated boot epoch, enforce physical
OEM safety separately, and arrange the Core registration/revocation protocol.
This class does not forward commands to hardware or prove transport identity.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from typing import Callable, Iterable

from jsonschema import Draft202012Validator, FormatChecker


_MAX_SAFE_INTEGER = 2**53 - 1
_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "spec" / "v0.1"
_COMMAND_SCHEMA = json.loads((_SCHEMA_DIR / "command-envelope.schema.json").read_text())
_EDGE_SCHEMA = json.loads((_SCHEMA_DIR / "edge-authority.schema.json").read_text())
_COMMAND_VALIDATOR = Draft202012Validator(_COMMAND_SCHEMA, format_checker=FormatChecker())
_EDGE_VALIDATOR = Draft202012Validator(_EDGE_SCHEMA, format_checker=FormatChecker())


@dataclass(frozen=True)
class Watermark:
    generation: int
    installation_sequence: int
    kind: str
    lease_id: str | None = None
    controller_id: str | None = None
    lease_valid_until: datetime | None = None
    deadline_mono: float | None = None


class EdgeFenceState:
    """In-memory reference fencing state; thread-safe within one process.

    `supported_control_domains` is local trusted configuration, not a claim
    made by an unauthenticated remote party. Empty configuration denies all.

    `trusted_wall_clock` MUST return aware UTC datetime when synchronized, or
    None when not trusted. With None, installations and commands fail closed.
    No network authentication is performed by this class.
    """

    def __init__(
        self,
        edge_id: str,
        edge_boot_id: str,
        *,
        supported_control_domains: Iterable[str] = (),
        monotonic_clock: Callable[[], float] = time.monotonic,
        trusted_wall_clock: Callable[[], datetime | None] | None = None,
    ):
        if not edge_id or not edge_boot_id:
            raise ValueError("Edge identity and boot epoch required")
        self.edge_id = edge_id
        self.edge_boot_id = edge_boot_id
        self.supported_control_domains = frozenset(supported_control_domains)
        if any(not isinstance(d, str) or not d for d in self.supported_control_domains):
            raise ValueError("Every declared control domain must be non-empty")
        self._monotonic_clock = monotonic_clock
        self._trusted_wall_clock = trusted_wall_clock
        self._lock = threading.Lock()
        self._marks: dict[tuple[str, str], Watermark] = {}
        self._seen_commands: dict[tuple[str, str], set[str]] = {}

    def _trusted_now(self) -> datetime | None:
        if self._trusted_wall_clock is None:
            return None
        try:
            now = self._trusted_wall_clock()
            if now is None or not isinstance(now, datetime) or now.utcoffset() is None:
                return None
            return now.astimezone(timezone.utc)
        except (ValueError, TypeError, OSError):
            return None

    @staticmethod
    def _parse_utc(timestamp: str) -> datetime | None:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if dt.utcoffset() is None:
                return None
            return dt.astimezone(timezone.utc)
        except (ValueError, AttributeError, TypeError, OverflowError):
            return None

    def accept_from_authenticated_core(self, message: dict) -> bool:
        """Legacy bool interface. Caller must authenticate the Core endpoint."""
        ok, _ = self.install_authority(message)
        return ok

    def install_authority(self, message: dict) -> tuple[bool, str]:
        """Install or revoke authority atomically; reject stale messages."""
        if not isinstance(message, dict) or not _EDGE_VALIDATOR.is_valid(message):
            return False, "malformed"
        if message.get("edge_id") != self.edge_id or message.get("edge_boot_id") != self.edge_boot_id:
            return False, "wrong_edge_epoch"
        kind = message.get("kind")
        if kind not in ("edge.authority_install", "edge.authority_revoke"):
            return False, "unsupported_message"
        domain = message["control_domain"]
        if domain not in self.supported_control_domains:
            return False, "domain_unsupported"
        gen = message["generation"]
        seq = message["installation_sequence"]
        key = (message["session_id"], domain)
        with self._lock:
            previous = self._marks.get(key)
            if previous is None:
                if seq != 1:
                    return False, "stale_installation"
            elif gen < previous.generation:
                return False, "stale_generation"
            elif gen == previous.generation:
                if previous.kind != "edge.authority_install" or kind != "edge.authority_install":
                    return False, "revoked"
                if seq <= previous.installation_sequence:
                    return False, "stale_installation"
                if (message.get("lease_id"), message.get("controller_id")) != (previous.lease_id, previous.controller_id):
                    return False, "lease_mismatch"
                # An expired generation cannot be revived by a delayed renewal.
                previous_wall = self._trusted_now()
                if previous_wall is None:
                    return False, "clock_untrusted"
                if (previous.deadline_mono is None or previous.lease_valid_until is None or
                    self._monotonic_clock() >= previous.deadline_mono or
                    previous_wall >= previous.lease_valid_until):
                    return False, "expired"
            elif seq != 1:
                return False, "stale_installation"

            if kind == "edge.authority_install":
                # Reject older generation's Lease reuse, including across revocation.
                if previous is not None and gen > previous.generation and message["lease_id"] == previous.lease_id:
                    return False, "lease_reused"
                wall_now = self._trusted_now()
                if wall_now is None:
                    return False, "clock_untrusted"
                until = self._parse_utc(message["lease_valid_until"])
                if until is None:
                    return False, "malformed"
                remaining = (until - wall_now).total_seconds()
                if remaining <= 0:
                    return False, "expired"
                ttl = message["max_local_ttl_ms"] / 1000.0
                mono_now = self._monotonic_clock()
                deadline = mono_now + min(ttl, remaining)
                mark = Watermark(gen, seq, kind, message["lease_id"], message["controller_id"], until, deadline)
                if previous is None or gen != previous.generation:
                    self._seen_commands[key] = set()
            else:
                # Tombstone keeps previous Lease ID only to detect immediate reuse.
                retired_lease_id = previous.lease_id if previous is not None else None
                mark = Watermark(gen, seq, kind, retired_lease_id, None)
                self._seen_commands.pop(key, None)
            self._marks[key] = mark
        return True, "accepted"

    def check_command(self, envelope: dict, authenticated_controller_id: str | None) -> tuple[bool, str]:
        """Validate one command and record its ID after all checks pass.

        Does not execute the action or implement an OEM safety decision.
        """
        if not isinstance(envelope, dict) or not _COMMAND_VALIDATOR.is_valid(envelope):
            return False, "malformed"
        if not isinstance(authenticated_controller_id, str) or authenticated_controller_id != envelope["controller_id"]:
            return False, "controller_mismatch"
        if envelope["control_domain"] not in self.supported_control_domains:
            return False, "domain_unsupported"
        key = (envelope["session_id"], envelope["control_domain"])
        with self._lock:
            mark = self._marks.get(key)
            if mark is None:
                return False, "no_authority"
            if mark.kind == "edge.authority_revoke":
                return False, "revoked"
            if envelope["lease_generation"] != mark.generation:
                return False, "stale_generation"
            if envelope["lease_id"] != mark.lease_id or authenticated_controller_id != mark.controller_id:
                return False, "lease_mismatch"
            wall_now = self._trusted_now()
            if wall_now is None:
                return False, "clock_untrusted"
            if (mark.lease_valid_until is None or mark.deadline_mono is None or
                self._monotonic_clock() >= mark.deadline_mono or wall_now >= mark.lease_valid_until):
                return False, "expired"
            already_seen = self._seen_commands.setdefault(key, set())
            if envelope["command_id"] in already_seen:
                return False, "duplicate_command"
            already_seen.add(envelope["command_id"])
            return True, "accepted"

    def snapshot(self, session_id: str, control_domain: str) -> Watermark | None:
        with self._lock:
            return self._marks.get((session_id, control_domain))
