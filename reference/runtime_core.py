"""Minimal, durable Twin Runtime Core reference for a simulated integration.

NOT production security: this module has NO authenticated transport, KYC, legal
consent verification, trusted external policy engine, cryptographic audit, live
human-presence proof, or hardware safety. Provisioning and controller identities
MUST be supplied by a trusted host. SQLite is a single-host reference store.

Core validates technical Grant/Policy/Session scopes, issues one Control Lease
per Session/Domain, advances durable generations, enqueues authenticated Edge
control messages, and emits ordered audit events in the same DB transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Callable, Iterator
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "spec" / "v0.1"
_VALIDATORS = {
    kind: Draft202012Validator(json.loads((_SCHEMA_DIR / f"{kind}.schema.json").read_text()),
                                 format_checker=FormatChecker())
    for kind in ("session", "representation-grant", "session-policy",
                 "compliance-policy", "control-lease", "runtime-event")
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("Naive timestamp not permitted")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class CoreDenied(ValueError):
    """Stable machine-readable denial reason (not a production HTTP API)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _validate(kind: str, value: dict) -> None:
    if not isinstance(value, dict) or not _VALIDATORS[kind].is_valid(value):
        raise CoreDenied("malformed_" + kind.replace("-", "_"))


class RuntimeCore:
    """Single-node SQLite reference Core with transactional fencing and audit.

    `db_path` MUST point to a persistent file. No `:memory:` database because
    a reboot must never reset authority generation. The wall clock is a trusted
    test/host input; Edge independently enforces its bounded monotonic TTL.
    """

    def __init__(self, db_path: str | Path, *, trusted_clock: Callable[[], datetime] = _utc_now):
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            raise ValueError("Persistent SQLite database required for Core fencing")
        self._clock = trusted_clock
        with self._transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS edges (
                    edge_id TEXT PRIMARY KEY, boot_id TEXT NOT NULL, domains TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edge_boot_history (
                    edge_id TEXT NOT NULL, boot_id TEXT NOT NULL,
                    PRIMARY KEY(edge_id,boot_id)
                );
                CREATE TABLE IF NOT EXISTS grants (
                    grant_id TEXT PRIMARY KEY, record TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    representation_subject_id TEXT NOT NULL, edge_id TEXT NOT NULL,
                    grant_ids TEXT NOT NULL, status TEXT NOT NULL,
                    presence_mode TEXT, operational_state TEXT NOT NULL,
                    policy_id TEXT, policy_version TEXT, compliance_id TEXT,
                    compliance_version TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policies (
                    kind TEXT NOT NULL, policy_id TEXT NOT NULL, version TEXT NOT NULL,
                    record TEXT NOT NULL, PRIMARY KEY(kind, policy_id, version)
                );
                CREATE TABLE IF NOT EXISTS lease_generations (
                    session_id TEXT NOT NULL, control_domain TEXT NOT NULL,
                    current_generation INTEGER NOT NULL,
                    PRIMARY KEY(session_id,control_domain)
                );
                CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    control_domain TEXT NOT NULL, record TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS leases_scope ON leases(session_id,control_domain);
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    session_sequence INTEGER NOT NULL, record TEXT NOT NULL,
                    UNIQUE(session_id,session_sequence)
                );
                CREATE TABLE IF NOT EXISTS edge_outbox (
                    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    edge_id TEXT NOT NULL, payload TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );
            """)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise CoreDenied("clock_untrusted")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _need(row: sqlite3.Row | None, kind: str) -> sqlite3.Row:
        if row is None:
            raise CoreDenied("unknown_" + kind)
        return row

    @staticmethod
    def _session(db: sqlite3.Connection, sid: str) -> sqlite3.Row:
        return RuntimeCore._need(db.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone(), "session")

    @staticmethod
    def _policy(db: sqlite3.Connection, kind: str, pid: str | None, version: str | None) -> dict:
        if not pid or not version:
            raise CoreDenied("missing_" + kind)
        row = db.execute("SELECT record FROM policies WHERE kind=? AND policy_id=? AND version=?",
                         (kind, pid, version)).fetchone()
        if not row:
            raise CoreDenied("missing_" + kind)
        record = json.loads(row["record"])
        if record["status"] != "active":
            raise CoreDenied("inactive_" + kind)
        return record

    def _audit(self, db: sqlite3.Connection, sid: str, kind: str, correlation_id: str, *,
               data: dict | None = None, **refs: str) -> None:
        seq = db.execute("SELECT COALESCE(MAX(session_sequence),0)+1 AS next_seq FROM events WHERE session_id=?",
                         (sid,)).fetchone()["next_seq"]
        event = {
            "event_id": "event_" + uuid4().hex,
            "event_type": kind,
            "occurred_at": _stamp(self._now()),
            "session_id": sid,
            "session_sequence": seq,
            "correlation_id": correlation_id,
            "data": data or {},
            **refs,
        }
        _validate("runtime-event", event)
        db.execute("INSERT INTO events(event_id,session_id,session_sequence,record) VALUES(?,?,?,?)",
                   (event["event_id"], sid, seq, _json(event)))

    @staticmethod
    def _enqueue(db: sqlite3.Connection, edge_id: str, payload: dict) -> None:
        db.execute("INSERT INTO edge_outbox(edge_id,payload) VALUES(?,?)", (edge_id, _json(payload)))

    @staticmethod
    def _next_generation(db: sqlite3.Connection, sid: str, domain: str) -> int:
        db.execute("""INSERT INTO lease_generations(session_id,control_domain,current_generation)
                      VALUES(?,?,1) ON CONFLICT(session_id,control_domain) DO UPDATE
                      SET current_generation=current_generation+1""", (sid,domain))
        value = db.execute("SELECT current_generation FROM lease_generations WHERE session_id=? AND control_domain=?",
                           (sid,domain)).fetchone()["current_generation"]
        if value > 2**53-1:
            raise CoreDenied("generation_exhausted")
        return value

    @staticmethod
    def _lease_records(db: sqlite3.Connection, sid: str, *, domain: str | None = None) -> list[dict]:
        if domain is None:
            rows = db.execute("SELECT record FROM leases WHERE session_id=?", (sid,)).fetchall()
        else:
            rows = db.execute("SELECT record FROM leases WHERE session_id=? AND control_domain=?", (sid,domain)).fetchall()
        return [json.loads(row["record"]) for row in rows]

    def _revoke_lease(self, db: sqlite3.Connection, lease: dict, reason: str, corr: str) -> None:
        if lease["status"] != "active":
            return
        lease["status"] = "revoked"
        db.execute("UPDATE leases SET record=? WHERE lease_id=?", (_json(lease),lease["lease_id"]))
        gen = self._next_generation(db, lease["session_id"], lease["control_domain"])
        edge = self._need(db.execute("SELECT * FROM edges WHERE edge_id=?",(lease["edge_id"],)).fetchone(), "edge")
        self._enqueue(db, lease["edge_id"],{
            "kind":"edge.authority_revoke","edge_id":lease["edge_id"],
            "edge_boot_id":edge["boot_id"],"session_id":lease["session_id"],
            "control_domain":lease["control_domain"],"generation":gen,
            "installation_sequence":1,"reason":reason,
        })
        self._audit(db,lease["session_id"],"lease.revoked",corr,
                    data={"reason":reason,"revoke_generation":gen},
                    lease_id=lease["lease_id"],controller_id=lease["controller_id"],
                    grant_id=lease["representation_grant_id"],control_domain=lease["control_domain"])

    def _revoke_session(self, db: sqlite3.Connection, sid: str, reason: str, corr: str) -> None:
        for lease in self._lease_records(db,sid):
            self._revoke_lease(db,lease,reason,corr)

    def _suspend(self, db: sqlite3.Connection, session: sqlite3.Row, reason: str, corr: str) -> None:
        sid=session["session_id"]
        self._revoke_session(db,sid,reason,corr)
        if session["status"] in ("active","ready"):
            db.execute("UPDATE sessions SET status='suspended',presence_mode=NULL,operational_state='standby' WHERE session_id=?",(sid,))
            if session["presence_mode"] is not None:
                self._audit(db,sid,"presence_mode.changed",corr,
                            data={"from_mode":session["presence_mode"],"to_mode":None,"reason":reason})
            self._audit(db,sid,"fallback.triggered",corr,data={"reason":reason,"action":"standby"})

    def register_edge(self, edge_id: str, edge_boot_id: str, supported_control_domains: list[str]) -> None:
        """Trusted local Edge provisioning. A boot change revokes and suspends affected Sessions."""
        if (not isinstance(edge_id,str) or not edge_id or not isinstance(edge_boot_id,str) or not edge_boot_id
            or not isinstance(supported_control_domains,list) or not supported_control_domains
            or any(not isinstance(x,str) or not x for x in supported_control_domains)
            or len(set(supported_control_domains))!=len(supported_control_domains)):
            raise CoreDenied("invalid_edge_registration")
        with self._transaction() as db:
            previous=db.execute("SELECT boot_id,domains FROM edges WHERE edge_id=?",(edge_id,)).fetchone()
            boot_changed=previous is not None and previous["boot_id"]!=edge_boot_id
            capabilities_changed=previous is not None and json.loads(previous["domains"])!=supported_control_domains
            if boot_changed and db.execute("SELECT 1 FROM edge_boot_history WHERE edge_id=? AND boot_id=?",
                                           (edge_id,edge_boot_id)).fetchone():
                raise CoreDenied("edge_boot_epoch_reused")
            db.execute("INSERT OR IGNORE INTO edge_boot_history(edge_id,boot_id) VALUES(?,?)",(edge_id,edge_boot_id))
            # Earlier installs addressed to an old boot must never be re-delivered.
            if boot_changed:
                db.execute("UPDATE edge_outbox SET acknowledged=1 WHERE edge_id=?",(edge_id,))
            db.execute("INSERT INTO edges(edge_id,boot_id,domains) VALUES(?,?,?) ON CONFLICT(edge_id) DO UPDATE SET boot_id=excluded.boot_id, domains=excluded.domains",
                       (edge_id,edge_boot_id,_json(supported_control_domains)))
            if boot_changed or capabilities_changed:
                reason="edge_restarted" if boot_changed else "edge_capabilities_changed"
                corr="operation_"+uuid4().hex
                # Both changes invalidate previously issued scoped authority.
                sessions=db.execute("SELECT * FROM sessions WHERE edge_id=?",(edge_id,)).fetchall()
                for session in sessions:
                    self._revoke_session(db,session["session_id"],reason,corr)
                    if session["status"] in ("active","ready"):
                        self._suspend(db,session,reason,corr)

    def provision_grant(self, grant: dict) -> None:
        """Trusted local admin input ONLY; no automatic acceptance of arbitrary client Grants."""
        _validate("representation-grant",grant)
        if _dt(grant["valid_from"]) >= _dt(grant["valid_until"]):
            raise CoreDenied("invalid_grant_window")
        with self._transaction() as db:
            existing=db.execute("SELECT record FROM grants WHERE grant_id=?",(grant["grant_id"],)).fetchone()
            if existing:
                raise CoreDenied("grant_already_exists")
            db.execute("INSERT INTO grants(grant_id,record) VALUES(?,?)",(grant["grant_id"],_json(grant)))

    def create_session(self, session_id: str, owner_id: str, representation_subject_id: str,
                       grant_ids: list[str], edge_id: str) -> None:
        if (not all(isinstance(x,str) and x for x in (session_id,owner_id,representation_subject_id,edge_id))
            or not isinstance(grant_ids,list) or not grant_ids or not all(isinstance(g,str) and g for g in grant_ids)
            or len(set(grant_ids)) != len(grant_ids)):
            raise CoreDenied("invalid_session_input")
        with self._transaction() as db:
            self._need(db.execute("SELECT * FROM edges WHERE edge_id=?",(edge_id,)).fetchone(),"edge")
            for gid in grant_ids:
                self._need(db.execute("SELECT * FROM grants WHERE grant_id=?",(gid,)).fetchone(),"grant")
            session={"session_id":session_id,"owner_id":owner_id,"representation_subject_id":representation_subject_id,
                     "edge_id":edge_id,"representation_grant_ids":grant_ids,"session_status":"created",
                     "presence_mode":None,"operational_state":"standby","created_at":_stamp(self._now())}
            _validate("session",session)
            try:
                db.execute("""INSERT INTO sessions(session_id,owner_id,representation_subject_id,edge_id,grant_ids,status,presence_mode,operational_state,created_at)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           (session_id,owner_id,representation_subject_id,edge_id,_json(grant_ids),"created",None,"standby",session["created_at"]))
            except sqlite3.IntegrityError as e:
                raise CoreDenied("session_already_exists") from e
            self._audit(db,session_id,"session.created","operation_"+uuid4().hex)

    def set_policies(self, session_id: str, session_policy: dict, compliance_policy: dict) -> None:
        _validate("session-policy",session_policy)
        _validate("compliance-policy",compliance_policy)
        if session_policy["session_id"]!=session_id or compliance_policy["session_id"]!=session_id:
            raise CoreDenied("wrong_session_policy")
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"]=="ended":
                raise CoreDenied("session_ended")
            for kind,policy in (("session_policy",session_policy),("compliance_policy",compliance_policy)):
                existing=db.execute("SELECT record FROM policies WHERE kind=? AND policy_id=? AND version=?",
                                    (kind,policy["policy_id"],policy["version"])).fetchone()
                if existing and existing["record"]!=_json(policy):
                    raise CoreDenied("policy_version_not_immutable")
                if not existing:
                    db.execute("INSERT INTO policies(kind,policy_id,version,record) VALUES(?,?,?,?)",
                               (kind,policy["policy_id"],policy["version"],_json(policy)))
            changed=(session["policy_id"],session["policy_version"],session["compliance_id"],session["compliance_version"]) != (
                session_policy["policy_id"],session_policy["version"],compliance_policy["policy_id"],compliance_policy["version"])
            if changed:
                corr="operation_"+uuid4().hex
                if session["status"] in ("active","ready"):
                    self._suspend(db,session,"policy_changed",corr)
                db.execute("UPDATE sessions SET policy_id=?,policy_version=?,compliance_id=?,compliance_version=? WHERE session_id=?",
                           (session_policy["policy_id"],session_policy["version"],compliance_policy["policy_id"],compliance_policy["version"],session_id))
                self._audit(db,session_id,"session_policy.changed",corr,data={"policy_id":session_policy["policy_id"],"version":session_policy["version"]})
                self._audit(db,session_id,"compliance_policy.changed",corr,data={"policy_id":compliance_policy["policy_id"],"version":compliance_policy["version"]})

    def _grant_for(self, db: sqlite3.Connection, session: sqlite3.Row, gid: str, mode: str, domain: str | None = None) -> dict:
        if gid not in json.loads(session["grant_ids"]):
            raise CoreDenied("grant_not_in_session")
        row=self._need(db.execute("SELECT record FROM grants WHERE grant_id=?",(gid,)).fetchone(),"grant")
        grant=json.loads(row["record"])
        if grant["status"]!="active" or not (_dt(grant["valid_from"]) <= self._now() < _dt(grant["valid_until"])):
            raise CoreDenied("grant_inactive_or_expired")
        if grant["owner_id"]!=session["owner_id"] or grant["authorized_subject"]!=session["representation_subject_id"]:
            raise CoreDenied("grant_subject_mismatch")
        if mode not in grant["allowed_presence_modes"]:
            raise CoreDenied("grant_mode_denied")
        if domain is not None and domain not in grant["allowed_control_domains"]:
            raise CoreDenied("grant_domain_denied")
        if grant["restrictions"]:
            raise CoreDenied("unknown_grant_restrictions")
        return grant

    def _context(self, db: sqlite3.Connection, session: sqlite3.Row, mode: str) -> tuple[dict,dict]:
        policy=self._policy(db,"session_policy",session["policy_id"],session["policy_version"])
        compliance=self._policy(db,"compliance_policy",session["compliance_id"],session["compliance_version"])
        if mode not in compliance["allowed_presence_modes"]:
            raise CoreDenied("compliance_mode_denied")
        if mode in ("bridge","totalmersion") and not policy.get("human_liveness_timeout_ms"):
            raise CoreDenied("missing_human_liveness_timeout")
        if not any(mode in auth["allowed_presence_modes"] for auth in policy["controller_authorizations"]):
            raise CoreDenied("no_mode_controller")
        return policy, compliance

    def prepare_session(self, session_id: str) -> None:
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"]!="created":
                raise CoreDenied("invalid_session_state")
            policy=self._policy(db,"session_policy",session["policy_id"],session["policy_version"])
            compliance=self._policy(db,"compliance_policy",session["compliance_id"],session["compliance_version"])
            if not any((mode in compliance["allowed_presence_modes"] and
                        any(mode in auth["allowed_presence_modes"] for auth in policy["controller_authorizations"]) and
                        self._grant_works(db,session,gid,mode))
                       for mode in ("autonomous","bridge","totalmersion") for gid in json.loads(session["grant_ids"])):
                raise CoreDenied("no_valid_representation_authority")
            db.execute("UPDATE sessions SET status='ready' WHERE session_id=?",(session_id,))
            self._audit(db,session_id,"session.ready","operation_"+uuid4().hex)

    def _grant_works(self,db:sqlite3.Connection,session:sqlite3.Row,gid:str,mode:str) -> bool:
        try:
            self._grant_for(db,session,gid,mode)
            return True
        except CoreDenied:
            return False

    def activate_session(self, session_id: str, presence_mode: str, *, owner_presence_confirmed: bool = False) -> None:
        if presence_mode not in ("autonomous","bridge","totalmersion"):
            raise CoreDenied("unknown_presence_mode")
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"] not in ("ready","suspended"):
                raise CoreDenied("invalid_session_state")
            self._context(db,session,presence_mode)
            if not any(self._grant_works(db,session,gid,presence_mode) for gid in json.loads(session["grant_ids"])):
                raise CoreDenied("no_valid_representation_authority")
            if presence_mode in ("bridge","totalmersion") and owner_presence_confirmed is not True:
                raise CoreDenied("owner_presence_not_confirmed")
            db.execute("UPDATE sessions SET status='active',presence_mode=?,operational_state='active' WHERE session_id=?",
                       (presence_mode,session_id))
            corr="operation_"+uuid4().hex
            self._audit(db,session_id,"session.started",corr,data={"mode":presence_mode})
            self._audit(db,session_id,"presence_mode.changed",corr,data={"from_mode":None,"to_mode":presence_mode})

    def change_mode(self, session_id: str, presence_mode: str, *, owner_presence_confirmed: bool = False) -> None:
        if presence_mode not in ("autonomous","bridge","totalmersion"):
            raise CoreDenied("unknown_presence_mode")
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"]!="active":
                raise CoreDenied("session_not_active")
            old=session["presence_mode"]
            if presence_mode==old:
                return
            self._context(db,session,presence_mode)
            if not any(self._grant_works(db,session,gid,presence_mode) for gid in json.loads(session["grant_ids"])):
                raise CoreDenied("no_valid_representation_authority")
            if presence_mode in ("bridge","totalmersion") and owner_presence_confirmed is not True:
                raise CoreDenied("owner_presence_not_confirmed")
            corr="operation_"+uuid4().hex
            self._revoke_session(db,session_id,"presence_mode_changed",corr)
            db.execute("UPDATE sessions SET presence_mode=? WHERE session_id=?",(presence_mode,session_id))
            self._audit(db,session_id,"presence_mode.changed",corr,
                        data={"from_mode":old,"to_mode":presence_mode})

    def issue_lease(self, session_id: str, controller_id: str, authenticated_controller_id: str,
                    control_domain: str, representation_grant_id: str, *,
                    requested_seconds: int = 30, max_local_ttl_ms: int = 1500) -> dict:
        """Trusted host MUST authenticate controller_id. Returns leased authority for audit/debug."""
        if not controller_id or authenticated_controller_id!=controller_id:
            raise CoreDenied("controller_mismatch")
        if (type(requested_seconds) is not int or not 1<=requested_seconds<=3600 or
            type(max_local_ttl_ms) is not int or not 1<=max_local_ttl_ms<=60000):
            raise CoreDenied("invalid_lease_timeout")
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"]!="active" or not session["presence_mode"]:
                raise CoreDenied("session_not_active")
            mode=session["presence_mode"]
            policy,compliance=self._context(db,session,mode)
            grant=self._grant_for(db,session,representation_grant_id,mode,control_domain)
            if control_domain not in compliance["allowed_control_domains"]:
                raise CoreDenied("compliance_domain_denied")
            if not any(auth["controller_id"]==controller_id and mode in auth["allowed_presence_modes"]
                       and control_domain in auth["allowed_control_domains"]
                       for auth in policy["controller_authorizations"]):
                raise CoreDenied("controller_not_authorized")
            edge=self._need(db.execute("SELECT * FROM edges WHERE edge_id=?",(session["edge_id"],)).fetchone(),"edge")
            if control_domain not in json.loads(edge["domains"]):
                raise CoreDenied("domain_unsupported")
            now=self._now()
            until=min(now+timedelta(seconds=requested_seconds),_dt(grant["valid_until"]))
            if until<=now:
                raise CoreDenied("grant_expired")
            corr="operation_"+uuid4().hex
            previous=[x for x in self._lease_records(db,session_id,domain=control_domain) if x["status"]=="active"]
            if len(previous)>1:
                raise CoreDenied("multiple_active_leases_detected")
            for lease in previous:
                self._revoke_lease(db,lease,"replaced",corr)
            generation=self._next_generation(db,session_id,control_domain)
            lease={"lease_id":"lease_"+uuid4().hex,"session_id":session_id,
                   "representation_grant_id":representation_grant_id,"controller_id":controller_id,
                   "control_domain":control_domain,"issued_at":_stamp(now),"valid_until":_stamp(until),
                   "status":"active","generation":generation,"installation_sequence":1,
                   "edge_id":edge["edge_id"],"edge_boot_id":edge["boot_id"],
                   "max_local_ttl_ms":max_local_ttl_ms}
            _validate("control-lease",lease)
            db.execute("INSERT INTO leases(lease_id,session_id,control_domain,record) VALUES(?,?,?,?)",
                       (lease["lease_id"],session_id,control_domain,_json(lease)))
            self._enqueue(db,edge["edge_id"],{
                "kind":"edge.authority_install","edge_id":edge["edge_id"],"edge_boot_id":edge["boot_id"],
                "session_id":session_id,"control_domain":control_domain,
                "generation":generation,"installation_sequence":1,"lease_id":lease["lease_id"],
                "controller_id":controller_id,"lease_valid_until":lease["valid_until"],
                "max_local_ttl_ms":max_local_ttl_ms})
            self._audit(db,session_id,"lease.issued",corr,
                        data={"generation":generation},lease_id=lease["lease_id"],
                        controller_id=controller_id,grant_id=representation_grant_id,control_domain=control_domain)
            if previous:
                self._audit(db,session_id,"control.handover",corr,
                            data={"previous_controller_id":previous[0]["controller_id"],"new_controller_id":controller_id},
                            lease_id=lease["lease_id"],control_domain=control_domain)
            return lease

    def revoke_grant(self, grant_id: str) -> None:
        """Local authority revocation; delivery to disconnected Edge is bounded by Edge TTL."""
        with self._transaction() as db:
            row=self._need(db.execute("SELECT record FROM grants WHERE grant_id=?",(grant_id,)).fetchone(),"grant")
            grant=json.loads(row["record"])
            if grant["status"]=="revoked":
                return
            grant["status"]="revoked"
            db.execute("UPDATE grants SET record=? WHERE grant_id=?",(_json(grant),grant_id))
            corr="operation_"+uuid4().hex
            sessions=db.execute("SELECT * FROM sessions").fetchall()
            for session in sessions:
                if grant_id not in json.loads(session["grant_ids"]):
                    continue
                self._audit(db,session["session_id"],"representation_grant.revoked",corr,grant_id=grant_id)
                for lease in self._lease_records(db,session["session_id"]):
                    if lease["status"]=="active" and lease["representation_grant_id"]==grant_id:
                        self._revoke_lease(db,lease,"grant_revoked",corr)
                if session["status"]=="active" and not any(
                    self._grant_works(db,session,gid,session["presence_mode"]) for gid in json.loads(session["grant_ids"])):
                    self._suspend(db,session,"grant_revoked",corr)

    def owner_disconnected(self, session_id: str) -> None:
        """Trusted simulator's explicit human-loss signal; not a heartbeat detector."""
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"]!="active" or session["presence_mode"] not in ("bridge","totalmersion"):
                raise CoreDenied("no_live_owner_mode")
            self._suspend(db,session,"owner_disconnected", "operation_"+uuid4().hex)

    def revoke_session_control(self, session_id: str, reason: str = "runtime_control_revoked") -> None:
        with self._transaction() as db:
            session=self._session(db,session_id)
            if session["status"]=="ended":
                raise CoreDenied("session_ended")
            corr="operation_"+uuid4().hex
            self._suspend(db,session,reason,corr)
            self._audit(db,session_id,"runtime_control.revoked",corr,data={"reason":reason})

    def session_snapshot(self, session_id: str) -> dict:
        with self._transaction() as db:
            row=self._session(db,session_id)
            obj={"session_id":row["session_id"],"owner_id":row["owner_id"],
                 "representation_subject_id":row["representation_subject_id"],"edge_id":row["edge_id"],
                 "session_status":row["status"],"presence_mode":row["presence_mode"],
                 "operational_state":row["operational_state"],"representation_grant_ids":json.loads(row["grant_ids"]),
                 "created_at":row["created_at"]}
            if row["policy_id"]:
                obj.update(session_policy_id=row["policy_id"],session_policy_version=row["policy_version"],
                           compliance_policy_id=row["compliance_id"],compliance_policy_version=row["compliance_version"])
            _validate("session",obj)
            return obj

    def active_leases(self, session_id: str) -> list[dict]:
        with self._transaction() as db:
            self._session(db,session_id)
            return [r for r in self._lease_records(db,session_id) if r["status"]=="active"]

    def events(self, session_id: str) -> list[dict]:
        with self._transaction() as db:
            self._session(db,session_id)
            rows=db.execute("SELECT record FROM events WHERE session_id=? ORDER BY session_sequence",(session_id,)).fetchall()
            return [json.loads(r["record"]) for r in rows]

    def pending_edge_updates(self, edge_id: str) -> list[tuple[int,dict]]:
        with self._transaction() as db:
            rows=db.execute("SELECT update_id,payload FROM edge_outbox WHERE edge_id=? AND acknowledged=0 ORDER BY update_id",(edge_id,)).fetchall()
            return [(r["update_id"],json.loads(r["payload"])) for r in rows]

    def acknowledge_edge_update(self, update_id: int, edge_id: str) -> None:
        """Trusted simulator only; a real transport must authenticate an Edge ACK."""
        with self._transaction() as db:
            db.execute("UPDATE edge_outbox SET acknowledged=1 WHERE update_id=? AND edge_id=?",(update_id,edge_id))
