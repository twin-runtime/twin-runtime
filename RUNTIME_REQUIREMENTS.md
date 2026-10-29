# Twin Runtime Requirements

**Status:** Requirements Baseline v0.1  
**Project:** Twin Runtime  
**License:** Apache-2.0  
**Related document:** `ARCHITECTURE.md`

---

## 1. Purpose

This document defines normative requirements for Twin Runtime v0.1.

Twin Runtime provides an open technical layer for:

**Identity → Representation → Presence → Control → Enforcement → Audit**

It integrates existing AI, realtime communication and robotics technologies rather than replacing them.

---

## 2. Requirement Keywords

The following terms are normative:

- **MUST** — mandatory for v0.1 compliance.
- **MUST NOT** — prohibited.
- **SHOULD** — strongly recommended unless an integration has a documented reason not to implement it.
- **SHOULD NOT** — normally avoided.
- **MAY** — optional.

---

## 3. Runtime Independence

Twin Runtime Core:

- **MUST** operate without Twin.rent Marketplace.
- **MUST NOT** require a proprietary Twin.rent service.
- **MUST NOT** require LiveKit.
- **MUST NOT** require LeRobot.
- **MUST NOT** require ROS 2.
- **MUST NOT** require a specific humanoid manufacturer.
- **MUST NOT** require a specific AI provider.
- **MUST NOT** require a specific Personality Provider.
- **MUST NOT** require a specific skill repository.

External technologies **MAY** be supported through integrations.

---

## 4. Required Core Concepts

Twin Runtime v0.1 **MUST** model at least:

- Identity Owner,
- Representation Provider,
- Representation Grant,
- Deployment,
- Session,
- Session Policy,
- Participant,
- Presence Mode,
- Operational State,
- Control Domain,
- Control Lease,
- Fallback Policy,
- Readiness,
- Compliance Policy,
- Audit Event.

---

## 5. Identity Owner

The Runtime:

- **MUST** support a stable identifier for the Identity Owner.
- **MUST** distinguish the Identity Owner from the current controller.
- **MUST** distinguish the Identity Owner from the robot or digital representation.
- **MUST** distinguish the Identity Owner from an AI agent.
- **MUST** distinguish the Identity Owner from the Representation Provider.
- **MUST** allow one Identity Owner to be associated with multiple Sessions.

The Runtime **MUST NOT** assume:

```text
Identity Owner = Operator = AI = Device
```

---

## 6. Representation Grant

A Representation Grant defines technical authorization to represent an Identity Owner.

A Representation Grant **MUST** provide or reference sufficient information to determine:

- represented Identity Owner,
- issuer / Representation Provider,
- authorized subject or controller class,
- validity period,
- allowed Presence Modes,
- applicable restrictions,
- grant status or revocation state.

A Representation Grant:

- **MUST NOT** automatically create a Control Lease.
- **MUST NOT** by itself authorize physical control.
- **MUST** be independently revocable.
- **MUST** be associated with a unique identifier.
- **MUST** be auditable.
- **MUST NOT** continue authorizing Runtime actions after it expires or is revoked.

Revocation or expiration of a Representation Grant **MUST** invalidate Runtime authority that depends on that Grant.

Any active Control Lease that depends on an invalid Representation Grant **MUST NOT** authorize new commands.

Twin Runtime **MUST NOT** claim that a Representation Grant is itself the underlying legal contract or commercial license.

---

## 7. Deployment

Twin Runtime **MUST** support a Deployment context for physical Twins.

A Deployment **MAY** contain multiple Sessions.

A Deployment **SHOULD** support metadata or references describing:

- planned time window,
- location or deployment context,
- device / Twin instance,
- applicable Compliance Policy,
- Readiness,
- operational status.

Runtime **MUST NOT** be responsible for:

- booking transportation,
- taxi services,
- logistics,
- venue management,
- payment for transport.

---

## 8. Session

Every Session **MUST** have:

- unique Session identifier,
- associated Identity Owner,
- current Presence Mode,
- current Operational State,
- active Control Leases,
- applicable Representation Grant or Grants,
- applicable Session Policy or policy reference,
- applicable Compliance Policy or policy reference,
- audit/event context.

A Session:

- **MAY** exist inside a Deployment,
- **MAY** be purely digital,
- **MUST NOT** assume one physical robot per Identity Owner.

### 8.1 Session Policy

Twin Runtime **MUST** support a Runtime-level Session Policy.

A Session Policy is separate from:

- the Representation Grant,
- the Compliance Policy,
- the Control Lease.

A Session Policy **MAY** constrain:

- actions,
- autonomy,
- Control Domains,
- required Identity Owner approval for selected actions,
- permitted fallback behaviour,
- observation or recording access,
- other Session-specific operating permissions.

Runtime **MUST** enforce an applicable Session Policy where the relevant action passes through Runtime authorization.

A Session Policy **MUST NOT** be treated as a replacement for legal agreements, Marketplace policy or applicable law.

---

## 9. Operational State

Operational State **MUST** be independent from Presence Mode.

The model **MUST** support an extensible state mechanism.

Non-normative examples include:

```text
transport
standby
ready
active
charging
degraded
unavailable
maintenance
```

Runtime **MUST NOT** interpret `charging`, `standby` or `transport` as Presence Modes.

---

## 10. Presence Modes

Twin Runtime v0.1 **MUST** support:

- `Autonomous`
- `Bridge`
- `TotalMersion`

Presence Mode transitions **MUST** be explicit.

Every Presence Mode transition **MUST** generate an audit event.

---

## 11. Autonomous

In Autonomous mode:

- AI or another autonomous controller **MAY** hold Control Leases.
- Autonomous behaviour **MUST** remain within the applicable Representation Grant.
- Autonomous behaviour **MUST** remain within the applicable Session Policy.
- Autonomous behaviour **MUST** remain within the effective Compliance Policy.
- Autonomous controllers **MUST NOT** receive authority solely because they are connected to the Session.

---

## 12. Bridge

Bridge **MUST** allow the Identity Owner to take over one or more Control Domains without requiring takeover of the entire Twin.

Example:

```text
conversation → Identity Owner
gesture      → Identity Owner
gaze         → Identity Owner

mobility     → AI
navigation   → AI
```

Bridge:

- **MUST** support explicit domain handover.
- **MUST** audit each handover.
- **MUST NOT** require simultaneous blending of human and AI commands within one Control Domain.
- **MAY** support external controllers that perform blending.

---

## 13. TotalMersion

During a TotalMersion period:

> The Identity Owner is live and controls the relevant high-level presence domains.

Runtime:

- **MUST** associate the relevant Control Leases with the Identity Owner.
- **MUST NOT** silently continue to label the Session as TotalMersion after Owner control is lost.
- **MUST** transition to another Presence Mode or Operational State when TotalMersion conditions are no longer satisfied.
- **MUST NOT** interpret OEM stabilization, balance or safety systems as Autonomous representation.

Technical heartbeat or network connectivity **MUST NOT** be described as proof that the human is physically attentive or consciously present.

---

## 14. Presence Mode Fallback

Automatic fallback from TotalMersion to Autonomous:

- **MUST** require explicit authorization.
- **MUST** be permitted by the applicable Representation Grant.
- **MUST** be permitted by Session policy.
- **MUST** generate a Presence Mode transition event.

If Autonomous fallback is not authorized, loss of Owner control **MUST** result in another declared behaviour such as:

- standby,
- mute,
- stop,
- safe-stop request,
- other configured fallback.

---

## 15. Control Domains

Twin Runtime **MUST** support extensible Control Domains.

Non-normative examples:

```text
conversation
voice
gaze
facial_expression
gesture
manipulation
mobility
navigation
```

Runtime v0.1 **MUST NOT** require all integrations to implement all domains.

An integration **MUST** declare which domains it supports.

---

## 16. Scoped Control Lease

Every Control Lease **MUST** be scoped at least to:

- Session,
- Control Domain,
- controller,
- validity period.

A Control Lease **MUST** support:

- issue,
- renew,
- revoke,
- expire.

Where applicable, it **MUST** support controller liveness or heartbeat.

Every Lease **MUST** have a unique identifier.

---

## 17. Single Controller Rule

Twin Runtime Core follows:

> **One active controller per Control Domain.**

Therefore:

```text
conversation → Controller A
mobility     → Controller B
```

is valid.

But two independent controllers simultaneously claiming authority over the same domain **MUST NOT** both be accepted by Runtime Core.

An external controller **MAY** internally combine several inputs and appear to Runtime as one controller.

---

## 18. Lease Expiration and Revocation

After a Lease expires or is revoked:

- new commands associated with that Lease **MUST** be rejected,
- stale commands **MUST NOT** regain control,
- the configured Fallback Policy **MUST** be evaluated,
- an audit event **MUST** be emitted.

Transport connection lifetime **MUST NOT** determine Lease validity.

A connected participant with an expired Lease **MUST NOT** retain control merely because the transport session remains open.

### 18.1 Controller of Record

Twin Runtime **MUST** expose the currently authoritative controller for each active Control Domain.

Controller-of-record state **MUST** be derived from current Runtime authority.

Transport connectivity by itself **MUST NOT** establish controller-of-record status.

When control authority changes, the controller-of-record state **MUST** change accordingly and the handover **MUST** remain auditable.

### 18.2 Session-wide Runtime Control Revocation

Twin Runtime **MUST** support authorized Session-wide revocation of Runtime control authority.

A Session-wide Runtime control revocation:

- **MUST** invalidate active Twin Runtime Control Leases for that Session,
- **MUST** cause new commands relying on those Leases to be rejected,
- **MUST** evaluate the configured Fallback Policy,
- **MUST** emit an audit event.

Runtime control revocation is separate from a physical OEM emergency stop.

Twin Runtime **MUST NOT** represent Runtime control revocation as proof that physical emergency-stop behaviour occurred unless an underlying integration explicitly confirms it.

---

## 19. Command Authorization

Before Runtime accepts a control action, the system **MUST** be able to determine that:

```text
required capability exists
AND
Representation Grant permits the action
AND
Session Policy permits the action
AND
Presence Mode permits the action
AND
Compliance Policy permits the action
AND
Control Lease is valid
AND
Edge Enforcement permits the action
```

Physical execution additionally remains subject to local OEM safety.

Failure of any required Runtime authorization condition **MUST** reject the action.

---

## 20. Command Context

A command or its trusted transport context **MUST** contain sufficient information to associate it with:

- Session,
- controller identity,
- Control Domain,
- active Lease.

The implementation **MUST** provide a mechanism to reject:

- commands from previous Lease holders,
- commands associated with expired Leases,
- delayed commands that are no longer authorized.

The exact sequencing mechanism is implementation-specific in v0.1.

---

## 21. Edge Enforcement Agent

Physical-control integrations claiming full Twin Runtime control enforcement **MUST** implement an enforcement point at or close to the robot.

The Edge Enforcement Agent **MUST**:

- validate relevant Lease state,
- reject unauthorized commands,
- reject expired authorization,
- reject stale controller authority,
- monitor required liveness,
- trigger configured fallback hooks,
- emit enforcement events.

The Edge Agent **MUST NOT** implement robot motion planning as a Runtime responsibility.

---

## 22. Enforcement Limitation

Twin Runtime **MUST NOT** claim guaranteed physical enforcement when:

- the Edge Enforcement Agent is bypassed,
- the OEM SDK can be accessed outside the controlled path,
- the integration does not implement required hooks,
- the robot stack ignores the enforcement result.

Documentation **MUST** state these limitations.

---

## 23. Safe-Stop Hook

A physical integration **MUST** provide a declared failure behaviour for control loss.

Where safe-stop is supported, the integration **MUST** expose a hook equivalent in purpose to:

```text
safe_stop()
```

Twin Runtime:

- **MUST NOT** define OEM-specific motor behaviour,
- **MUST NOT** directly implement balance control,
- **MUST NOT** assume that `stop` means the same thing on all humanoids.

OEM integration code is responsible for translating the hook into the correct local behaviour.

---

## 24. Fallback Policy

A Session or Control Domain **MUST** be able to declare fallback behaviour.

Examples may include:

```text
conversation → mute
gesture      → neutral pose
mobility     → safe stop
navigation   → stop
Owner lost   → standby
Owner lost   → authorized Autonomous mode
```

Fallback execution **MUST** be auditable.

Fallback **MUST NOT** silently change semantic Presence Mode.

---

## 25. Local Safety Boundary

Twin Runtime **MUST** treat local physical safety systems as higher authority than Runtime control.

Runtime **MUST NOT** require bypassing:

- emergency stop,
- collision protection,
- actuator limits,
- balance control,
- stabilization,
- OEM safety constraints.

A local safety controller **MAY** reject a Runtime-authorized action.

---

## 26. Low-Level Motor Control

Twin Runtime public network interfaces **MUST NOT** expose direct raw actuator or torque control as a general Runtime API.

OEM integrations **MAY** use low-level control locally when required and when protected by the robot's safety architecture.

---

## 27. Observation and Telemetry

Twin Runtime **MUST** support bidirectional operation.

Integrations **MAY** expose observations including:

- vision,
- audio,
- depth,
- proximity,
- orientation,
- IMU,
- acceleration,
- temperature,
- thermal sensing,
- tactile sensing,
- force,
- pressure,
- torque,
- finger sensors,
- olfactory sensing,
- battery,
- charging state,
- actuator telemetry.

The modality model **MUST** remain extensible.

---

## 28. Data Plane Separation

Twin Runtime Core **MUST NOT** require high-bandwidth sensor streams to pass through Runtime Core.

High-volume streams **MAY** use external transports such as:

- realtime media systems,
- ROS,
- OEM transports,
- robotics middleware.

Runtime **MUST** be able to maintain metadata or references describing:

- stream identity,
- Session,
- source,
- modality,
- access authorization,
- availability.

---

## 29. Observation Authorization

Observation access **MUST** be independently authorizable.

Possession of a control Lease **MUST NOT** automatically imply unrestricted access to:

- video,
- audio,
- recordings,
- sensory streams,
- historical data.

Compliance and privacy policies **MAY** restrict observation separately from control.

---

## 30. Readiness

Runtime **MUST** support Readiness reporting.

Readiness **MAY** include:

- available capabilities,
- battery level,
- charging state,
- estimated remaining runtime,
- thermal state,
- network status,
- sensor availability,
- actuator availability,
- degraded functionality.

An integration **MUST NOT** report a capability as available when it knows the capability is unavailable.

---

## 31. Energy

Twin Runtime **MUST NOT** implement battery charging or battery-management logic.

It **SHOULD** expose energy-related state when available from an integration.

Runtime **MAY** compare declared deployment requirements with reported energy availability.

---

## 32. Compliance Policy

Twin Runtime **MUST** support an externally supplied Compliance Policy.

A Compliance Policy **MAY** constrain:

- recording,
- streaming,
- sensor use,
- autonomy,
- mobility,
- geofencing,
- data retention,
- disclosure,
- supervision requirements.

Runtime **MUST** reject an action when an effective Compliance Policy explicitly prohibits it.

---

## 33. Legal Interpretation Boundary

Twin Runtime:

- **MUST NOT** determine which law applies,
- **MUST NOT** provide legal interpretation,
- **MUST NOT** claim regulatory certification merely because a technical policy is enforced.

A Compliance Policy Provider or other external authority is responsible for translating applicable rules into technical constraints.

---

## 34. Presence Disclosure

Runtime **MUST** expose sufficient current state for an integration to communicate:

- current Presence Mode,
- current controller per relevant domain,
- fallback state where applicable.

Runtime **MAY** support integrations for:

- visual indicators,
- displays,
- audio disclosure,
- UI indicators,
- machine-readable status.

The disclosure hardware itself is outside Runtime Core.

---

## 35. Audit Events

Runtime **MUST** emit structured events for at least:

- Session creation,
- Representation Grant activation,
- Representation Grant revocation,
- Session Policy change,
- Session-wide Runtime control revocation,
- Presence Mode transition,
- Lease issue,
- Lease renewal,
- Lease revocation,
- Lease expiration,
- controller handover,
- command rejection,
- fallback activation,
- safe-stop request,
- Compliance Policy change,
- Readiness change.

---

## 36. Command Lifecycle Audit

Runtime **MUST** distinguish where technically possible between:

```text
requested
authorized
dispatched
acknowledged
rejected
unknown
```

Runtime **MUST NOT** label a command as physically executed unless the integration provides explicit confirmation sufficient to support that statement.

---

## 37. Audit Persistence

Runtime Core **MUST** emit audit events.

The reference implementation **SHOULD** provide a mechanism to persist them.

Persisted Runtime audit events **SHOULD** follow a logically append-only model.

Previously persisted Runtime audit events **SHOULD NOT** be silently rewritten during normal operation.

Cryptographic tamper-evidence is **NOT REQUIRED** for v0.1.

It **MAY** be added in future versions.

---

## 38. MultiPresence

The Runtime data model **MUST** allow:

> one Identity Owner → multiple simultaneous Sessions.

Sessions **MUST** remain independently addressable.

Each Session **MUST** maintain its own:

- Presence Mode,
- Leases,
- Representation context,
- Session Policy context,
- Operational State,
- Compliance context,
- audit events.

Runtime **MUST** provide a mechanism for an authorized caller to enumerate active Sessions associated with a specific Identity Owner.

v0.1 **MUST NOT** require orchestration of all Sessions into one Experience Layer.

---

## 39. Personality Integration

Twin Runtime v0.1:

- **MUST** allow external Personality Providers to be integrated,
- **MUST NOT** require a proprietary Twin personality format,
- **MUST NOT** implement its own foundational Personality Engine.

Personality integration **MAY** provide references to:

- communication style,
- memory,
- knowledge,
- voice,
- behavioural constraints.

---

## 40. Skill and Policy Integration

Twin Runtime:

- **MUST** allow external skill or policy providers,
- **MUST NOT** define a mandatory proprietary universal skill format in v0.1,
- **MUST NOT** require Hugging Face, LeRobot or another specific ecosystem.

An integration **SHOULD** be able to declare the capabilities it provides or requires.

---

## 41. Experience Integration

Runtime events and observations **SHOULD** be consumable by future Experience Providers.

Runtime v0.1 **MUST NOT** require:

- G-Brain,
- global memory aggregation,
- opportunity extraction,
- multi-session summarization.

---

## 42. Transport Integration

A Transport Integration **MUST** provide enough trusted information for Runtime to associate incoming control traffic with the authenticated controller or an authenticated mapping.

Transport Integrations **MUST NOT** determine Twin Runtime Presence semantics independently.

Transport technology **MAY** change without changing core Runtime semantics.

---

## 43. Robot Integration

A Robot Integration **MUST** declare:

- supported Control Domains,
- supported capabilities,
- supported observation modalities where applicable,
- failure / fallback hooks,
- safe-stop capability where applicable.

A Robot Integration **MUST NOT** claim support for functionality it cannot enforce or provide.

---

## 44. Unsupported Features

When an integration does not support a Runtime capability or Presence requirement, it **MUST** report the feature as unsupported.

Runtime **MUST NOT** silently downgrade semantics.

Example:

If TotalMersion requirements cannot be satisfied, the integration **MUST NOT** represent the Session as TotalMersion.

---

## 45. Versioning

Public Runtime interfaces and normative schemas **MUST** be versioned.

Breaking changes **MUST** be identifiable.

Integrations **MUST** be able to declare which Runtime version they support.

Semantic Versioning **SHOULD** be used for public Runtime releases.

---

## 46. Reference Implementation

Twin Runtime v0.1 **MUST** include a runnable reference implementation of the Core.

The reference implementation **MUST** be usable without a physical humanoid.

It **MUST** include a dummy or simulated integration sufficient to test:

- Sessions,
- Presence Modes,
- Control Leases,
- handover,
- expiration,
- rejection,
- fallback,
- audit.

At least one real external integration **SHOULD** be provided for v0.1 or shortly thereafter.

The specific external technology is not mandated by this requirements document.

---

## 47. Developer Experience

The project **MUST** provide enough documentation for an external developer to:

1. run the Runtime,
2. create a Session,
3. register a controller,
4. issue a Control Lease,
5. send an authorized action,
6. observe rejection of an unauthorized action,
7. implement an integration,
8. run conformance tests.

An integration template **SHOULD** be provided.

---

## 48. Conformance Suite

Twin Runtime **MUST** provide automated conformance tests.

At minimum they **MUST** test:

1. unauthorized commands are rejected,
2. expired Lease commands are rejected,
3. revoked Lease commands are rejected,
4. stale previous-controller commands are rejected,
5. Control Domain handover works,
6. Presence Mode transition is explicit,
7. TotalMersion does not silently survive Owner-control loss,
8. declared fallback is invoked,
9. unsupported capabilities are reported,
10. applicable Session Policy restrictions are enforced,
11. applicable Compliance Policy restrictions are enforced,
12. Representation Grant revocation prevents dependent Runtime authority from continuing,
13. Session-wide Runtime control revocation invalidates active Session Leases,
14. controller-of-record reflects current Runtime authority,
15. audit events represent authorization decisions,
16. multiple Sessions may reference the same Identity Owner,
17. active Sessions can be enumerated for an authorized Identity Owner lookup.

---

## 49. Conformance Boundary

Passing Twin Runtime conformance tests means:

> the implementation follows Twin Runtime software semantics for the declared features.

It **MUST NOT** be presented as:

- physical robot safety certification,
- legal compliance certification,
- regulatory approval,
- insurance certification.

---

## 50. Security Requirements

Runtime implementations:

- **MUST NOT** hard-code credentials or secrets in public repositories,
- **MUST** support secure deployment of credentials through external configuration,
- **SHOULD** use existing authentication and encryption mechanisms rather than inventing new cryptography,
- **SHOULD** minimize trust placed in remote clients,
- **SHOULD** fail closed when control authorization cannot be verified.

---

## 51. Open Source Boundary

The Apache-2.0 Runtime scope **MUST** include the technical components required for standalone Runtime operation.

A user **MUST NOT** need Twin.rent Marketplace to:

- create a local Session,
- issue a test Representation Grant,
- issue a Control Lease,
- run enforcement,
- run conformance tests.

Commercial Marketplace services remain outside Runtime Core.

---

## 52. Non-Goals for v0.1

Twin Runtime v0.1 **MUST NOT** attempt to become:

- a replacement for ROS 2,
- a replacement for LeRobot,
- a realtime media platform,
- a robot motion-control framework,
- an emergency-stop implementation,
- an SLAM system,
- a navigation system,
- a battery-management system,
- a proprietary Personality Engine,
- a universal robot Skill format,
- a Skill Marketplace,
- a Robot Cloud,
- a logistics platform,
- a legal interpretation engine,
- a global Experience / G-Brain platform.

---

## 53. v0.1 Minimum Success Criteria

Twin Runtime v0.1 is technically meaningful when an external developer can demonstrate:

```text
1. create Identity Owner
2. issue Representation Grant
3. create Session
4. enter Autonomous mode
5. AI receives conversation Lease
6. Identity Owner takes conversation Lease
7. Runtime rejects stale AI command
8. gesture remains under AI control
9. Owner disconnects
10. declared fallback executes
11. Presence Mode changes explicitly
12. audit reconstructs what happened
```

The same core behaviour **MUST** be demonstrable using the dummy/simulated integration without requiring a physical humanoid.

---

## 54. Architectural Invariants

The following rules are foundational for Twin Runtime v0.1:

1. **Representation authority and control authority are separate.**
2. **A Representation Grant does not automatically create a Control Lease.**
3. **One active controller exists per Control Domain.**
4. **Presence Mode and Operational State are separate concepts.**
5. **TotalMersion cannot silently become Autonomous.**
6. **Transport connectivity does not equal control authority.**
7. **Local OEM safety always has final authority over physical execution.**
8. **Runtime Core must remain independent of Twin.rent Marketplace.**
9. **Runtime does not replace existing robotics, AI or transport stacks.**
10. **One Identity Owner may participate through multiple simultaneous Twin Sessions.**
11. **Personality, Skills and Experience remain extensible external layers.**
12. **Software conformance is not physical safety or regulatory certification.**
13. **Session Policy is distinct from Representation Grant, Compliance Policy and Control Lease.**
14. **Expired or revoked Representation Grants cannot continue authorizing dependent Runtime actions.**
15. **Controller-of-record is derived from current Runtime authority, not transport connectivity.**
16. **Session-wide Runtime control revocation is distinct from physical OEM emergency stop.**
