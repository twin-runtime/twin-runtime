"""Local-only interactive Twin Runtime Core + Edge simulation.

Run from the repo root: python -m examples.demo_web --port 8765
Open http://127.0.0.1:8765

This is an EXPLICITLY SIMULATED, unauthenticated, single-host developer demo.
Browser actions are trusted demo triggers, NOT proof of a real human identity,
controller transport, heartbeat, consent, OEM command, or robot safety.
Do NOT expose it publicly or reuse this HTTP adapter in production.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
from typing import Callable
from urllib.parse import urlsplit
from uuid import uuid4

from reference.edge_fence import EdgeFenceState
from reference.runtime_core import CoreDenied, RuntimeCore

_ASSETS = Path(__file__).resolve().parent / "web_demo"
_ACTIONS = frozenset({
    "start", "join", "disconnect", "ai_speak", "ai_wave",
    "owner_wave", "stale_ai_wave", "stale_owner_wave", "reset",
})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class DemoState:
    """Thread-safe UI adapter over actual reference Core and Edge classes.

    Trust in the local click is simulated. Its purpose is to exercise real
    authorization/fencing state transitions, not establish real identity.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.RLock()
        self._clock = clock
        self._monotonic = monotonic
        self.token = secrets.token_urlsafe(32)
        self._temporary: tempfile.TemporaryDirectory | None = None
        with self._lock:
            self._new_demo()

    def close(self) -> None:
        with self._lock:
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None

    def _new_demo(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
        self._temporary = tempfile.TemporaryDirectory(prefix="twin-runtime-web-")
        self.core = RuntimeCore(Path(self._temporary.name) / "runtime.sqlite", trusted_clock=self._clock)
        self.edge_id = "edge-demo"
        self.edge_boot_id = "boot-" + uuid4().hex
        self.session_id = "session-demo"
        self.grant_id = "grant-demo"
        self.leases: dict[str, dict] = {}
        self.stale_ai_gesture: dict | None = None
        self.stale_owner_gesture: dict | None = None
        self.command_checks: list[dict] = []
        self.last_command: dict | None = None

        self.edge = EdgeFenceState(
            self.edge_id,
            self.edge_boot_id,
            supported_control_domains=["conversation", "gesture"],
            monotonic_clock=self._monotonic,
            trusted_wall_clock=self._clock,
        )
        self.core.register_edge(self.edge_id, self.edge_boot_id, ["conversation", "gesture"])
        now = self._clock()
        self.core.provision_grant({
            "grant_id": self.grant_id,
            "provider_id": "trusted-local-demo",
            "owner_id": "owner-demo",
            "authorized_subject": "simulation-twin",
            "valid_from": stamp(now - timedelta(minutes=1)),
            "valid_until": stamp(now + timedelta(hours=2)),
            "allowed_presence_modes": ["autonomous", "bridge"],
            "allowed_control_domains": ["conversation", "gesture"],
            "status": "active",
            "restrictions": {},
        })
        self.core.create_session(
            self.session_id, "owner-demo", "simulation-twin", [self.grant_id], self.edge_id,
        )
        self.core.set_policies(self.session_id, {
            "policy_id": "session-policy-demo",
            "session_id": self.session_id,
            "version": "1",
            "status": "active",
            "controller_authorizations": [
                {"controller_id": "ai-agent", "allowed_presence_modes": ["autonomous", "bridge"],
                 "allowed_control_domains": ["conversation", "gesture"]},
                {"controller_id": "human-owner", "allowed_presence_modes": ["bridge"],
                 "allowed_control_domains": ["gesture"]},
            ],
            "fallback_autonomous_allowed": False,
            "human_liveness_timeout_ms": 2000,
        }, {
            "policy_id": "compliance-demo",
            "session_id": self.session_id,
            "version": "1",
            "status": "active",
            "allowed_presence_modes": ["autonomous", "bridge"],
            "allowed_control_domains": ["conversation", "gesture"],
        })
        self.core.prepare_session(self.session_id)

    def _sync_edge(self) -> None:
        # Simulated synchronous trusted-delivery path, not a network transport.
        for update_id, message in self.core.pending_edge_updates(self.edge_id):
            accepted, reason = self.edge.install_authority(message)
            if not accepted:
                raise RuntimeError("Edge update rejected: " + reason)
            self.core.acknowledge_edge_update(update_id, self.edge_id)

    def _lease(self, controller: str, domain: str) -> dict:
        return self.core.issue_lease(
            self.session_id, controller, controller, domain, self.grant_id,
            requested_seconds=900, max_local_ttl_ms=60000,
        )

    def _command(self, lease: dict | None, kind: str, label: str) -> None:
        if lease is None:
            raise CoreDenied("demo_lease_not_available")
        controller = lease["controller_id"]
        envelope = {
            "command_id": "command_" + uuid4().hex,
            "session_id": self.session_id,
            "controller_id": controller,
            "control_domain": lease["control_domain"],
            "lease_id": lease["lease_id"],
            "lease_generation": lease["generation"],
            "issued_at": stamp(self._clock()),
            "payload": {"simulated_action": kind},
        }
        accepted, reason = self.edge.check_command(envelope, controller)
        check = {
            "when": stamp(self._clock()),
            "label": label,
            "controller": controller,
            "domain": lease["control_domain"],
            "generation": lease["generation"],
            "accepted": accepted,
            "reason": reason,
            "kind": kind,
        }
        # This is a local Edge decision log, NOT a durable Core audit event.
        self.command_checks.insert(0, check)
        self.command_checks = self.command_checks[:14]
        self.last_command = check

    def perform(self, action: str) -> dict:
        if action not in _ACTIONS:
            raise CoreDenied("unknown_demo_action")
        with self._lock:
            status = self.core.session_snapshot(self.session_id)
            if action == "reset":
                self._new_demo()
            elif action == "start":
                if status["session_status"] != "ready":
                    raise CoreDenied("demo_already_started")
                self.core.activate_session(self.session_id, "autonomous")
                self.leases = {
                    "conversation": self._lease("ai-agent", "conversation"),
                    "gesture": self._lease("ai-agent", "gesture"),
                }
                self._sync_edge()
            elif action == "join":
                if status["session_status"] != "active" or status["presence_mode"] != "autonomous":
                    raise CoreDenied("demo_not_autonomous")
                self.stale_ai_gesture = self.leases["gesture"]
                # This click SIMULATES an authenticated owner-presence signal.
                self.core.change_mode(self.session_id, "bridge", owner_presence_confirmed=True)
                self.leases = {
                    "conversation": self._lease("ai-agent", "conversation"),
                    "gesture": self._lease("human-owner", "gesture"),
                }
                self.stale_owner_gesture = self.leases["gesture"]
                self._sync_edge()
            elif action == "disconnect":
                if status["session_status"] != "active" or status["presence_mode"] != "bridge":
                    raise CoreDenied("demo_not_bridge")
                # This click SIMULATES a trusted disconnect notification.
                self.core.owner_disconnected(self.session_id)
                self._sync_edge()
            elif action == "ai_speak":
                self._command(self.leases.get("conversation"), "speak", "AI says hello")
            elif action == "ai_wave":
                if status["presence_mode"] != "autonomous":
                    raise CoreDenied("demo_not_autonomous")
                self._command(self.leases.get("gesture"), "wave", "AI waves")
            elif action == "owner_wave":
                if status["presence_mode"] != "bridge":
                    raise CoreDenied("demo_not_bridge")
                self._command(self.leases.get("gesture"), "wave", "Owner waves")
            elif action == "stale_ai_wave":
                self._command(self.stale_ai_gesture, "wave", "Old AI lease tries to wave")
            elif action == "stale_owner_wave":
                self._command(self.stale_owner_gesture, "wave", "Disconnected owner tries to wave")
            return self.snapshot()

    def snapshot(self) -> dict:
        with self._lock:
            session = self.core.session_snapshot(self.session_id)
            active = {x["control_domain"]: x for x in self.core.active_leases(self.session_id)}
            domains = []
            for domain in ("conversation", "gesture"):
                lease = active.get(domain)
                mark = self.edge.snapshot(self.session_id, domain)
                edge_effective = bool(
                    mark and mark.kind == "edge.authority_install" and
                    mark.lease_id == (lease or {}).get("lease_id") and
                    mark.deadline_mono is not None and
                    self._monotonic() < mark.deadline_mono and
                    mark.lease_valid_until is not None and
                    self._clock() < mark.lease_valid_until
                )
                domains.append({
                    "name": domain,
                    "controller": lease["controller_id"] if lease else None,
                    "generation": lease["generation"] if lease else (mark.generation if mark else None),
                    "lease_id": lease["lease_id"] if lease else None,
                    "edge_authorized_now": edge_effective,
                })
            return {
                "session": session,
                "domains": domains,
                "audit": self.core.events(self.session_id)[-16:][::-1],
                "command_checks": self.command_checks[:],
                "last_command": self.last_command,
                "csrf_token": self.token,
                "simulation": True,
                "integration": "local Python Core + Edge, no physical robot",
            }


def make_handler(service: DemoState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "TwinRuntimeLocalDemo/0.1"
        sys_version = ""

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                             "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: dict) -> None:
            self._send(status, json.dumps(value, separators=(",", ":")).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _local_host(self) -> bool:
            host = self.headers.get("Host", "").split(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def do_GET(self) -> None:
            if not self._local_host():
                return self._json(403, {"error": "localhost_only"})
            path = urlsplit(self.path).path
            if path == "/api/state":
                return self._json(200, service.snapshot())
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8")}
            entry = files.get(path)
            if entry is None:
                return self._json(404, {"error": "not_found"})
            self._send(200, (_ASSETS / entry[0]).read_bytes(), entry[1])

        def do_POST(self) -> None:
            if not self._local_host():
                return self._json(403, {"error": "localhost_only"})
            if urlsplit(self.path).path != "/api/action":
                return self._json(404, {"error": "not_found"})
            origin = self.headers.get("Origin")
            if origin and origin not in (
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            ):
                return self._json(403, {"error": "invalid_origin"})
            if (self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    != "application/json"):
                return self._json(415, {"error": "json_required"})
            if not secrets.compare_digest(self.headers.get("X-Demo-Token", ""), service.token):
                return self._json(403, {"error": "invalid_demo_token"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 1024:
                    return self._json(413, {"error": "invalid_request_size"})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or set(data) != {"action"} or not isinstance(data["action"], str):
                    return self._json(400, {"error": "invalid_request"})
                return self._json(200, service.perform(data["action"]))
            except CoreDenied as ex:
                return self._json(409, {"error": ex.reason})
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as ex:
                return self._json(400, {"error": "invalid_request", "detail": str(ex)})

        def log_message(self, fmt: str, *args: object) -> None:
            # Do not log request headers, including the demo token.
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only Twin Runtime visual simulation")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    service = DemoState()
    try:
        with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(service)) as server:
            print(f"Twin Runtime simulated web demo: http://127.0.0.1:{server.server_port}", flush=True)
            print("Local simulation only. No authenticated user / live robot / OEM safety.", flush=True)
            server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


if __name__ == "__main__":
    main()
