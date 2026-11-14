# Twin Runtime

**Open runtime for licensed human presence across AI agents, digital representations and physical robots.**

> Status: **Pre-alpha / experimental reference implementation**

Twin Runtime is an open-source interoperability and control layer for systems in which a specific human or organization is represented through AI, digital Twins or physical robots.

The project focuses on one problem:

> How can identity, representation authority, presence, control, enforcement and audit work consistently across different AI systems, transports and robot platforms?

Twin Runtime is licensed under **Apache-2.0**.

## Try the live demo locally

The interactive browser demo uses a **real local Python Runtime Core and Edge reference implementation**, not a static mockup. It simulates a handover from Autonomous AI control to a human Identity Owner and suspends the Session after a simulated disconnect.

**Requirements:** Python 3.11 or newer. No physical robot, LLM API key, Twin.rent account or commercial service is required.

1. Select **Code > Download ZIP** on GitHub and extract it, or clone the repository.
2. Open a terminal in the **repository root**, the folder containing `requirements-tests.txt`. With **Download ZIP**, that folder is normally named **`twin-runtime-main`**. With `git clone`, it is usually **`twin-runtime`**.
3. Create a private Python virtual environment, install test dependencies, then run the demo:

**Windows (PowerShell):**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tests.txt
.\.venv\Scripts\python.exe -m examples.demo_web --port 8765
```

**macOS / Linux:**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-tests.txt
./.venv/bin/python -m examples.demo_web --port 8765
```

On Debian/Ubuntu, if `python3 -m venv .venv` reports that `ensurepip` is unavailable, install the distribution's `python3-venv` package and rerun the first command. **Do not use `--break-system-packages`.**

Open **http://127.0.0.1:8765** on the **same computer** and click **Run Full Scenario** for a one-click, repeatable simulation of all three modes, accepted commands and denied stale/revoked commands ending in a Suspended Session. Or click **Start session** for manual exploration. Try **Join as Identity Owner** (Bridge), then **Enter TotalMersion** for full simulated owner control of conversation and gesture. Use **Test old AI conversation lease** to verify denial, or **Simulate disconnect** for a separate fail-closed safety test. Speech is visual only; no audio is generated. Press **Ctrl+C** in the terminal to stop the server.

To run the automated tests from the repository root, using the same virtual environment:

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

**macOS / Linux:**

```bash
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

**Security:** This demo listens on `127.0.0.1` only. It does not implement real identity verification, user authentication, OEM safety, actual human-presence detection, or robot control. AI responses and connection events are scripted. **Do not expose the demonstration server to the internet or use it to control physical hardware.**

Detailed scenario and limitations: [examples/README.md](examples/README.md).
---

## Why Twin Runtime

Current robotics and AI stacks already provide many of the underlying technologies:

- robot control and motion,
- realtime communications,
- AI models and agents,
- navigation,
- sensors and telemetry,
- OEM safety systems.

Twin Runtime does not replace them.

It defines a common layer above them for:

- representation authority,
- Session semantics,
- Presence Modes,
- scoped Control Leases,
- controller handover,
- Runtime policy enforcement,
- fallback behaviour,
- control provenance,
- audit and events,
- integration with external AI, transport and robotics systems.

---

## Core Model

Twin Runtime follows this conceptual chain:

```text
Identity
   ↓
Representation
   ↓
Presence
   ↓
Control
   ↓
Enforcement
   ↓
Audit
```

External systems continue to provide:

```text
AI → Skills → Transport → Robotics → Hardware → Safety
```

Local OEM safety always remains above Runtime control authority.

---

## Key Concepts

### Identity Owner

The human or organization whose identity or presence is represented.

The Identity Owner is separate from the current operator, AI agent, robot, device or Representation Provider.

### Representation Grant

Technical authorization to represent an Identity Owner under defined conditions.

A Representation Grant does **not** automatically grant control.

### Session

An independently addressable instance of presence and interaction.

One Identity Owner may have multiple simultaneous Sessions.

### Session Policy

Runtime-level permissions and restrictions applied to a specific Session.

Session Policy is separate from Representation Grant, Compliance Policy and Control Lease.

### Presence Modes

Twin Runtime v0.1 defines three primary modes:

- **Autonomous** - AI or another autonomous controller operates authorized domains.
- **Bridge** - AI may control some domains while the Identity Owner observes or takes over selected domains.
- **TotalMersion** - the Identity Owner is live and controls the relevant high-level presence domains.

Presence Mode transitions are explicit.

### Control Lease

Temporary authority over one Control Domain inside one Session.

Core rule:

> **One active controller per Control Domain.**

Example:

```text
conversation → Identity Owner
gesture      → Identity Owner
mobility     → AI
navigation   → AI
```

### Controller of Record

Runtime exposes which Controller currently holds authority for each active Control Domain.

Transport connectivity alone does not establish control authority.

### Runtime Control Revocation

Twin Runtime supports Session-wide revocation of Runtime control authority.

This invalidates active Runtime Control Leases, rejects new commands relying on them, evaluates configured fallback behaviour and emits audit events.

This mechanism is separate from the physical OEM emergency stop.

---

## Architecture Direction

```text
Identity Owner
      │
      ▼
Representation Provider
      │
      ▼
Representation Grant
      │
      ▼
┌─────────────────────────┐
│      TWIN RUNTIME       │
│                         │
│ Session                 │
│ Session Policy          │
│ Presence Mode           │
│ Control Leases          │
│ Fallback Policies       │
│ Readiness               │
│ Audit & Events          │
└─────────────────────────┘
      │             ▲
      │ control     │ observations
      ▼             │
Transport / Integration Layer
      │
      ▼
Edge Enforcement Agent
      │
      ▼
ROS 2 / LeRobot / OEM SDK
      │
      ▼
Robot / Digital Twin
```

No specific transport, robotics framework, AI provider, robot manufacturer or marketplace is a mandatory dependency of Twin Runtime Core.

---

## MultiPresence

Twin Runtime is designed so that one Identity Owner may participate through multiple simultaneous Sessions.

```text
Identity Owner
 ├── Session A
 ├── Session B
 ├── Session C
 └── Session D
```

Each Session remains independently authorized and controlled.

The Runtime can expose active Sessions associated with an Identity Owner without requiring a global shared-memory or Experience layer.

---

## Audit

Runtime emits structured events for authorization and control decisions.

The reference architecture uses a logically append-only audit model: previously persisted Runtime events should not be silently rewritten during normal operation.

Cryptographic tamper-evidence is **not required** by Twin Runtime v0.1.

---

## What Twin Runtime Does Not Replace

Twin Runtime v0.1 is not intended to replace:

- ROS 2,
- LeRobot,
- OEM robot SDKs,
- WebRTC or other realtime transports,
- SLAM or navigation systems,
- motion controllers,
- stabilization or balance controllers,
- collision avoidance,
- emergency-stop systems,
- AI models,
- personality engines,
- skill ecosystems,
- legal or regulatory interpretation systems.

Passing Twin Runtime conformance tests is not physical robot safety certification or regulatory certification.

---

## Independence from Twin.rent Marketplace

Twin Runtime is an open technical layer.

It must operate without Twin.rent Marketplace and without any proprietary Twin.rent service.

Twin.rent Marketplace may act as one Representation Provider, but other providers and self-hosted environments must also be possible.

Commercial marketplace functions such as KYC, contracts, listings, bookings, payments and revenue sharing are outside Runtime Core.

---

## Repository Documents

- [Architecture](ARCHITECTURE.md) - system boundaries and architectural model
- [Runtime Requirements](RUNTIME_REQUIREMENTS.md) - normative v0.1 requirements
- [Identity and Grant Contract](docs/IDENTITY_GRANT_CONTRACT.md) - `owner_id`, `authorized_subject`, provider identifiers and current trust limits
- [RFC-0001](rfcs/RFC-0001-session-representation-control-lease.md) - Session, Representation Grant and Control Lease model
- [RFC-0002](rfcs/RFC-0002-identifiers-events-data-model.md) - identifiers, events and minimal data model
- [RFC-0003](rfcs/RFC-0003-command-lease-grant-session.md) - command authority, Grant/Lease binding, Edge fencing and interruption
- [Demo guide](examples/README.md) - local browser scenario and limitations
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [License](LICENSE)

---

## Current Development Stage

The repository includes an **experimental, single-host reference implementation** with:

1. versioned JSON Schemas for Core objects and Edge authority messages,
2. a SQLite-backed Runtime Core for Session, Grant/Policy checks, Lease fencing and audit,
3. an in-process simulated integration with no physical robot,
4. reference Edge command acceptance and rejection logic,
5. automated Python tests,
6. an interactive localhost browser demo.

**Not yet implemented:** authenticated external transports and providers, production-grade access control, actual human-presence verification, robot/OEM integration or physical safety enforcement. Open interfaces and conformance are still evolving; passing tests does not establish production readiness.

Next milestones: make the demo easy to run and independently review, then prototype an external AI-controller adapter and one independently verifiable robotics/transport integration.

---

## Design Principles

1. Representation authority and control authority are separate.
2. A Representation Grant does not automatically create a Control Lease.
3. One active controller exists per Control Domain.
4. Presence Mode and Operational State are separate concepts.
5. TotalMersion cannot silently become Autonomous.
6. Transport connectivity does not equal control authority.
7. Local OEM safety has final authority over physical execution.
8. Runtime Core remains independent of Twin.rent Marketplace.
9. Runtime integrates existing AI, transport and robotics stacks rather than replacing them.
10. One Identity Owner may participate through multiple simultaneous Sessions.
11. Session-specific policy and external compliance policy remain distinct.
12. Software conformance is not physical safety or regulatory certification.

---

## Contributing

Twin Runtime is currently in an early architecture and implementation phase.

Before contributing, read [CONTRIBUTING.md](CONTRIBUTING.md) and the current RFCs.

Significant semantic or architectural changes require an Issue and follow the [RFC process](rfcs/README.md) before implementation. See [CONTRIBUTING.md](CONTRIBUTING.md#where-to-start) for the single Issue / PR / RFC / Security path.

---

## License

Apache License 2.0.

See [LICENSE](LICENSE).
