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

## Local visual demo (Core + Edge, interactive browser)

From repository root, after installing `requirements-tests.txt`:

```bash
python -m examples.demo_web --port 8765
```

Open **http://127.0.0.1:8765** on the same computer. The local web UI calls
real `RuntimeCore` and `EdgeFenceState` Python instances; it is **not** a
static mockup. There is no LLM/API billing or external browser dependency.

1. Click **Start session** to issue two autonomous AI Control Leases.
2. Try **AI speaks** and **AI waves**. The Edge validates each command.
3. Click **Join as Identity Owner**. This **simulates** a trusted presence
   signal. Bridge mode issues new Leases: AI for conversation, Owner for gesture.
4. Click **Test old AI lease** to observe Edge reject the stale generation.
5. Click **Owner waves**, then **Simulate disconnect**.
6. Click **Test disconnected owner** to see command rejection; the Session
   is suspended, the Core has revoked Leases, and Audit shows the transition.
7. Click **Reset demonstration** to start a fresh isolated local simulation.

The stylized robot illustration performs a short visual wave or nod only when
an Edge command check is accepted. It is **not** a robotics physics simulator,
rendering of a real OEM robot, or proof of hardware execution.

**Important limits:** The server deliberately binds only to `127.0.0.1` and
uses a demo-only CSRF token. There is no actual user authentication, identity
verification, robot transport, physical human-presence detection, OEM safety,
or real command execution. The owner join/disconnect and AI responses are
scripted, trusted local test signals. Edge Command Check results are kept in
volatile UI memory, separately from ordered durable Core audit events. Leases
have bounded local Edge TTL (60 s); after it expires Edge denies commands
until new authority is issued. Do not expose this server to the internet.
