"""Tiny reference fencing state machine, NOT production Edge execution safety.

The calling transport MUST authenticate Core and MUST validate JSON Schema before
accepting a message. This class only illustrates ordering within one Edge boot;
it does not implement offline expiry, physical safety or secure sessions.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Watermark:
    generation: int
    installation_sequence: int
    kind: str
    lease_id: str | None = None
    controller_id: str | None = None


class EdgeFenceState:
    def __init__(self, edge_id: str, edge_boot_id: str):
        if not edge_id or not edge_boot_id:
            raise ValueError("Edge identity and boot epoch required")
        self.edge_id = edge_id
        self.edge_boot_id = edge_boot_id
        self._marks: dict[tuple[str, str], Watermark] = {}

    def accept_from_authenticated_core(self, message: dict) -> bool:
        """Return True if a validated installation/revocation is newer.

        Rejects boot mismatch, stale generation, stale same-generation
        renewal, same-generation controller replacement and tombstone revival.
        Does NOT check that the message came from an authenticated Core.
        """
        if message.get("edge_id") != self.edge_id or message.get("edge_boot_id") != self.edge_boot_id:
            return False
        kind = message.get("kind")
        if kind not in ("edge.authority_install", "edge.authority_revoke"):
            return False
        gen = message.get("generation")
        seq = message.get("installation_sequence")
        if type(gen) is not int or gen < 1 or type(seq) is not int or seq < 1:
            return False
        session_id = message.get("session_id")
        domain = message.get("control_domain")
        if not isinstance(session_id, str) or not session_id or not isinstance(domain, str) or not domain:
            return False
        key = (session_id, domain)
        previous = self._marks.get(key)
        if previous is not None:
            if gen < previous.generation:
                return False
            if gen == previous.generation:
                if previous.kind != "edge.authority_install" or kind != "edge.authority_install":
                    return False
                if seq <= previous.installation_sequence:
                    return False
                if (message.get("lease_id"), message.get("controller_id")) != (previous.lease_id, previous.controller_id):
                    return False
            elif kind == "edge.authority_install" and seq != 1:
                # A new generation starts its own installation sequence.
                return False
        if kind == "edge.authority_install":
            lease_id = message.get("lease_id")
            controller_id = message.get("controller_id")
            if not isinstance(lease_id, str) or not lease_id or not isinstance(controller_id, str) or not controller_id:
                return False
        else:
            if previous and gen <= previous.generation:
                return False
            lease_id, controller_id = None, None
        self._marks[key] = Watermark(gen, seq, kind, lease_id, controller_id)
        return True

    def snapshot(self, session_id: str, control_domain: str) -> Watermark | None:
        return self._marks.get((session_id, control_domain))
