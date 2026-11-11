# Twin Runtime simulated reference flow (Core v0.1, experimental)

From the repository root, after installing `requirements-tests.txt`:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m examples.demo_simulated_handover
```

The demo runs entirely in one Python process with a temporary SQLite database.
It shows a local trusted-admin Grant and two separate policies, an active
Autonomous Session, an AI Control Lease, a switch to Bridge with a **new** Owner
Lease, stale-command rejection, simulated Owner disconnect, a suspended Session,
Edge revocation and ordered audit events. No Twin.rent Marketplace is needed.

**Not a production deployment.** Local calls stand in for authenticated Core
and Controller transports. `owner_presence_confirmed=True` and
`owner_disconnected(...)` simulate trusted liveness signals; **no actual heartbeat
or physical presence verification is implemented**. Edge performs no robot
control or local OEM safety. Cross-host messaging, outbox delivery/ACK identity,
cryptographic integrity, policy-provider trust and exact physical fallback
are outside this slice. Remote revocation is not instantaneous if Edge is
unreachable; Edge enforces bounded local expiry.

Schemas in `spec/v0.1/` describe draft v0.1 Core objects, not a published
interoperability certification. `reference/runtime_core.py` persists fencing
counters, Leases and Session audit to SQLite for a single-host demo, not a
multi-node distributed Core. It accepts Grants only through a **trusted local
provisioning call**; untrusted clients must never be allowed to call it directly.
