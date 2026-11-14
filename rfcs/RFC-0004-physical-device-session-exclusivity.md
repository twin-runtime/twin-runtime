# RFC-0004: Exclusive Physical-Device Control Across Sessions

**Status:** Draft  
**Target:** Twin Runtime v0.1  
**Issue:** [#6 - Exclusive physical robot control across Runtime Sessions](https://github.com/twin-runtime/twin-runtime/issues/6)  
**Related:** [RFC-0001](RFC-0001-session-representation-control-lease.md), [RFC-0003](RFC-0003-command-lease-grant-session.md), [Architecture](../ARCHITECTURE.md), [Runtime Requirements](../RUNTIME_REQUIREMENTS.md)

---

## 1. Summary and decision requested

**Option A (proposed): one physical robot may have no more than one authoritative controlling Session at any instant.** Within that Session, separate Controllers may control different Control Domains according to existing Control Leases.

An independently authorized observation-only Session may watch the same robot, but may not command it. A Deployment may contain successive controlling Sessions. Digital and other physical representations remain independently concurrent.

This constraint is **in addition to**, not a replacement for, RFC-0001's one active Controller per Control Domain per Session rule.

**Status warning:** This Draft proposes future normative requirements. It does not assert that the current Python Core, Edge, schemas, transport or OEM integration implement them. An Accepted RFC is required before normative implementation.

## 2. Problem and evidence in the current reference implementation

Current `reference/runtime_core.py` issues/replaces Control Leases by `(session_id, control_domain)`. Current `reference/edge_fence.py` likewise indexes installed authority by `(session_id, control_domain)`. As a result, Session A and Session B may independently install and use authority for the same `edge_id`, even when the underlying physical robot is the same.

Session-level fencing alone does not enforce physical-device exclusivity. A controller-of-record for each Session/Domain does not establish a single controller-of-record for the robot.

This is a **reference-model authorization gap**. The repository currently has no physical robot integration, tested safety certification, production identity authentication or proof of real-world exploit.

## 3. Goals

- Enforce at most one effective **controlling Session** for each physical robot, across all of its Control Domains.
- Distinguish control authority from observation-only access.
- Make Session handoff atomic from the perspective of the physical Edge, including delayed and reordered messages.
- Fail closed when exclusivity cannot be established or verified.
- Preserve Bridge (multiple Controllers in different domains of *one* Session), MultiPresence across different devices, and sequential Sessions in one Deployment.
- Support precise, auditable ownership changes, denial reasons and failure conditions.

## 4. Non-goals

- Changing the definition of TotalMersion: **in v0.1 it remains genuine live presence of the Identity Owner**.
- Adding delegated TotalMersion or a fourth Presence Mode.
- Implementing Marketplace bookings, licensing contracts, G-Brain or experience/memory capture.
- Defining a universal robot identification format, multi-robot Edge topology, OEM motion APIs, robot safety certification or production-grade transport.
- Claiming that an observation-only Session can issue physical commands.

Future design must distinguish the represented **Identity Owner**, the authenticated **Controller**, and the physical device. An authorized operator is not implicitly the Identity Owner and does not make delegated control into TotalMersion.

## 5. Physical-device identity and scope (v0.1 proposal)

For the v0.1 reference, **one `edge_id` is provisioned as the exclusive authority endpoint for one independently controllable physical robot**. All commands to that robot must pass through that Edge.

This is a *trusted deployment assumption*, not a property currently established by a cryptographic device identity. The host MUST NOT map two independent physical robots onto the same exclusive-control slot, or expose multiple Edge identities that can independently control the same robot.

A future Edge agent serving multiple devices will require a stable physical-resource identifier and a separate RFC/contract amendment. A distinct `edge_boot_id` identifies a boot epoch, **not** a different robot.

The current reference Core also uses an Edge for simulated non-hardware scenarios. This RFC's physical-device invariant applies to **physical deployments**; it must not inadvertently block independent digital representations with no shared physical actuator. The future model must explicitly distinguish a physical Edge from a purely digital execution endpoint before enforcing a common schema.

## 6. Controlling versus observing

A **controlling Session** is a Session authorized to install and exercise physical-device control through an Edge. The exclusive slot is acquired **before** an effective Control Lease is installed, not simply when a Session is created or when a client connects.

An **observation-only Session** may receive authorized observations/telemetry without any effective command Lease for that device. Such access does not acquire the physical control slot. Observation and recording permissions remain governed by applicable policies.

Option A holds the slot for the whole controlling Session across **all** command domains, including conversation/voice/gesture and mobility/navigation. A second Session cannot bypass exclusivity by requesting a different domain.

**Open question:** precisely which domains are non-command observations and how a Session is marked observation-only in v0.1. Do not assume existing schemas or code already implement this classification.

## 7. Proposed authority and lifecycle invariants

1. Each physical robot has at most one effective controlling `session_id` at any instant, enforced locally by the Edge before command acceptance.
2. Controller-to-domain allocation remains Session-scoped. Two controllers may control distinct domains within the **same** active controlling Session.
3. Core issuance alone MUST NOT be treated as effective physical control until Edge installation/fencing has been confirmed for that Session and its exclusive device epoch.
4. A conflicting Session's Lease issuance or installation MUST be rejected until exclusivity is safely transferred; merely revoking a DB row is insufficient.
5. A transfer MUST fence all prior controlling-Session authority for the entire device, not only a single `(session_id, domain)` pair.
6. Stale commands, delayed installs, duplicate messages and late acknowledgements from prior Sessions MUST NOT reactivate control.
7. Physical command acceptance MUST fail closed when the Edge cannot validate a current device-level controlling Session, boot identity and authority epoch.
8. The OEM's physical safety interlocks and emergency stop remain independent and higher priority than Runtime authority.

These are proposed requirements **conditional on RFC acceptance**.

## 8. Cross-Session handoff proposal

Conceptual sequence (not an implemented wire protocol):

1. Core receives a request to transfer device control from Session A to Session B.
2. Core authenticates the caller; validates B's Representation Grant, Session/Compliance Policies, mode and Controller authorizations.
3. Core reserves the device for an ordered transfer without granting B effective Edge authority.
4. Edge fences the **entire previous controlling Session** using a device-level monotonically increasing authority epoch, irrespective of its individual domain generations.
5. Edge applies the configured non-commanding fallback/stop and acknowledges that A can no longer command this device.
6. Only after that fencing acknowledgement may Edge accept the new epoch and install B's scoped Leases.
7. Core records the transfer and corresponding Edge acknowledgements in an auditable state transition.

If acknowledgement or safety preconditions fail, **B does not become effective**. On loss of connectivity, the Edge must fail closed when the bounded authorization lifetime expires and use OEM-defined safety behavior. Replaying an old message after reconnect MUST NOT restore prior control.

**Implementation design needed:** a durable per-device monotonic epoch / session fence across reboot; authenticated, ordered Edge installation acknowledgements; explicit acquisition/release state; concurrency across processes; crash recovery; and exact handoff/stop semantics. Current per-`(session_id, domain)` generations are insufficient. Edge-level slot acquisition alone is not a substitute for persistent device fencing.

The v0.1 reference may need a conservative stop-before-start transition; uninterrupted handover is **not** a v0.1 guarantee.

## 9. Failure and concurrency behavior to specify

| Situation | Required result proposed |
| --- | --- |
| Two Sessions request the same physical Edge concurrently | At most one acquires effective command authority |
| Two Sessions request different Control Domains on same robot | Second controlling Session rejected under Option A |
| Valid prior-session command arrives after transfer | Edge rejects it |
| Delayed prior-session install arrives after transfer | Edge rejects it even if prior Lease had not expired |
| Core crashes during transfer | Edge cannot accept two Sessions; unproven authority fails closed |
| Edge reboots / reconnects | No stale session or epoch is revived |
| Revocation cannot reach Edge | No promise of instantaneous revocation; bounded TTL and fail-closed local enforcement |
| Observation-only Session exists | No command authority; does not occupy exclusive slot |
| Two different robots / Edges | Independent controlling Sessions permitted |
| One Session in Bridge | Different Controllers may hold different domains under policy |
| Concurrent purely digital MultiPresence | Unaffected unless sharing a physical resource |

Some failure cases depend on unavailable integration mechanisms; they are target acceptance criteria, **not current guarantees**.

## 10. Alternatives and trade-offs

**Option A (recommended for v0.1): one controlling Session per physical device.** Simpler invariant and clearer device-wide fencing. Limits parallel, independent sessions on one humanoid, even if their domains do not overlap. Within-Session Bridge and passive observation remain possible.

**Option B (deferred): exclusivity per `(physical_device_id, control_domain)`.** More flexible, but requires an explicit domain taxonomy, cross-domain safety coupling rules, and a design for inter-session arbitration. Unsafe to approximate with the current Session/Domain map.

**No change (rejected for physical control):** per-Session authority permits concurrent conflicting command paths to one robot.

## 11. Acceptance criteria for an implementation PR (after acceptance)

- Tests demonstrate two Sessions targeting the same Edge cannot hold effective control, including across distinct domains.
- Core and Edge jointly enforce exclusivity, not Core only.
- Handoff fences previous Session; stale commands, delayed installs and reordered acknowledgements cannot revive it.
- Simultaneous requests, process restart and Edge reboot do not create dual control.
- Connectivity loss expires/halts command authority according to documented bounded local TTL, without claiming immediate remote revocation.
- Same-Session Bridge continues to support separate Controller/Domain allocations.
- Concurrent Sessions on distinct physical Edges succeed.
- Purely digital concurrent Sessions remain supported.
- Observation-only Sessions cannot command and do not block control (once observation mechanism exists).
- Audit records selected controlling Session, resource, transfer and denials without leaking unnecessary personal data.
- Existing Python CI matrix and DCO checks pass.
- Documentation accurately separates implemented behavior, deployment assumptions and unsupported physical safety claims.

## 12. Decisions required before marking Accepted

1. Is `edge_id` an acceptable **one-Edge-per-physical-robot** trust assumption in v0.1?
2. How does the Core distinguish physical from digital execution contexts without changing their semantics?
3. What exactly acquires/releases the device slot: first effective Lease, explicit session control claim, or another state?
4. How is one device epoch durably persisted, authenticated and fenced across Core/Edge restarts?
5. What Edge acknowledgement is sufficient to begin a new controlling Session after old authority is fenced?
6. How are observation-only Sessions recognized and authorized?
7. Which fallback/stop guarantees are actually testable with the current Python reference versus only with a future OEM adapter?

## 13. Follow-up work once accepted

1. Amend RFC-0001 and Runtime Requirements with the accepted device-level invariant.
2. Specify any schema, Edge message and state-model changes in a separate design/implementation PR.
3. Implement reference Core, Edge and deterministic regression tests.
4. Verify that the physical controls remain clearly **reference-only**, without production-hardware claims.

**Deferred horizon (not v0.1 scope):** authorized employee operators, provenance of human versus autonomous control, and G-Brain experience provenance. Those concepts must not silently redefine TotalMersion or introduce experimental memory-transfer claims into the Runtime reference.
