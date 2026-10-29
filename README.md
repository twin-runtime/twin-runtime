# Twin Runtime

**Open runtime for licensed human presence across AI agents, digital representations and physical robots.**

> Status: **Pre-alpha / architecture and specification phase**

Twin Runtime is an open-source interoperability and control layer for systems in which a specific human or organization is represented through AI, digital Twins or physical robots.

The project focuses on one problem:

> How can identity, representation authority, presence, control, enforcement and audit work consistently across different AI systems, transports and robot platforms?

Twin Runtime is licensed under **Apache-2.0**.

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

Cryptographic tamper-evidence, distributed ledgers and blockchain are **not required** by Twin Runtime v0.1.

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
- [RFC-0001](rfcs/RFC-0001-session-representation-control-lease.md) - Session, Representation Grant and Control Lease model
- [RFC-0002](rfcs/RFC-0002-identifiers-events-data-model.md) - identifiers, events and minimal data model
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [License](LICENSE)

---

## Current Development Stage

The repository currently defines the architectural and normative foundation for Twin Runtime.

The next implementation steps are:

1. normative JSON Schemas,
2. Runtime Core reference implementation,
3. dummy / simulated integration,
4. Edge Enforcement reference component,
5. conformance tests,
6. first external robotics or transport integration.

The initial schemas are expected to cover at least:

- Session,
- Representation Grant,
- Session Policy,
- Control Lease,
- Runtime Event.

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

Significant semantic or architectural changes should be proposed through the RFC process before implementation.

---

## License

Apache License 2.0.

See [LICENSE](LICENSE).
