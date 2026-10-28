# RFC-0001: Session, Representation Grant and Control Lease Model

**Status:** Draft  
**Target:** Twin Runtime v0.1  
**Related:** `ARCHITECTURE.md`, `RUNTIME_REQUIREMENTS.md`

---

## 1. Summary

This RFC defines the conceptual relationship between:

- Identity Owner,
- Representation Grant,
- Session,
- Control Domain,
- Control Lease,
- controller,
- Presence Mode.

The central rule is:

> **Authorization to represent an Identity Owner and authority to control a Twin are separate.**

A Representation Grant allows representation.

A Control Lease allows temporary control over a specific Control Domain inside a specific Session.

Neither concept replaces the other.

---

## 2. Goals

This RFC defines:

- how a Session is created and identified,
- how representation authority is attached to a Session,
- how controllers receive temporary authority,
- how control authority expires or is revoked,
- how handover works,
- how stale controllers are prevented from regaining control,
- how Presence Modes relate to Control Leases.

---

## 3. Non-Goals

This RFC does not define:

- JSON schemas,
- REST or RPC endpoints,
- cryptographic credential format,
- specific identity provider,
- specific transport,
- robot motion APIs,
- OEM safe-stop implementation,
- commercial licensing contracts,
- billing,
- Marketplace logic.

Those are handled by later specifications or integrations.

---

## 4. Core Entities

### 4.1 Identity Owner

The person or organization being represented.

```text
IdentityOwner
```

The Identity Owner is not automatically:

- the controller,
- the Operator,
- the AI agent,
- the device,
- the Representation Provider.

---

### 4.2 Representation Provider

A trusted source that can issue representation authorization.

Examples may include:

- Twin.rent Marketplace,
- another identity/licensing service,
- a self-hosted test authority.

```text
RepresentationProvider
```

Twin Runtime Core must not depend on one specific provider.

---

### 4.3 Representation Grant

A Representation Grant states that a subject is allowed to represent an Identity Owner under defined conditions.

Conceptually:

```text
RepresentationGrant
    grant_id
    identity_owner
    issuer
    authorized_subject
    validity
    allowed_presence_modes
    restrictions
    status
```

The exact serialization is defined later.

A Representation Grant:

- does not itself create a Session,
- does not itself create a Control Lease,
- does not automatically authorize physical control.

---

### 4.4 Session

A Session is an active Twin presence context.

Conceptually:

```text
Session
    session_id
    identity_owner
    presence_mode
    operational_state
    representation_context
    compliance_context
    participants
    control_leases
```

A Session is independently addressable.

One Identity Owner may have multiple simultaneous Sessions.

---

### 4.5 Controller

A Controller is a source of actions.

Examples:

```text
Identity Owner
AI Agent
teleoperator
policy
orchestrator
external control system
```

A Controller must not receive authority solely because it is connected.

Authority comes from a valid Control Lease.

---

### 4.6 Control Domain

A Control Domain is a logical area of control.

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

The domain model must remain extensible.

---

### 4.7 Control Lease

A Control Lease grants one Controller temporary authority over one Control Domain within one Session.

Conceptually:

```text
ControlLease
    lease_id
    session_id
    control_domain
    controller_id
    issued_at
    valid_until
    status
```

Additional fields may be added later.

---

## 5. Relationship Model

The conceptual relationship is:

```text
Identity Owner
      │
      ▼
Representation Grant
      │
      ▼
    Session
      │
      ├── Control Domain: conversation
      │       └── Control Lease → Controller A
      │
      ├── Control Domain: gesture
      │       └── Control Lease → Controller A
      │
      ├── Control Domain: mobility
      │       └── Control Lease → Controller B
      │
      └── Control Domain: navigation
              └── Control Lease → Controller B
```

---

## 6. Representation Grant Rules

A Session representing an Identity Owner must have valid representation authority.

The Runtime must be able to determine:

```text
who is represented
who issued the authorization
who or what is authorized
when the authorization is valid
which Presence Modes are allowed
whether the Grant has been revoked
```

A Grant may authorize:

- a human,
- an AI system,
- a class of approved controllers,
- another technical subject.

The exact subject model is defined later.

---

## 7. Grant Does Not Imply Lease

This is a foundational invariant.

```text
Representation Grant ≠ Control Lease
```

Example:

An AI agent may be authorized to represent an Identity Owner in Autonomous mode.

That does not mean it automatically controls:

```text
mobility
gesture
conversation
navigation
```

Each required Control Domain still needs a valid Control Lease.

---

## 8. Lease Scope

A Control Lease is scoped to:

```text
Session
+
Control Domain
+
Controller
+
Validity period
```

A Lease from Session A cannot be used in Session B.

A Lease for `conversation` cannot authorize `mobility`.

A Lease belonging to Controller A cannot authorize Controller B.

---

## 9. Single Controller Rule

For Runtime Core:

> **One active Controller per Control Domain per Session.**

Example:

```text
conversation → Owner
gesture      → Owner
mobility     → AI
navigation   → AI
```

This is valid.

The following is not valid as two independent Runtime authorities:

```text
mobility → Owner
mobility → AI
```

If a system blends multiple inputs, it must appear to Runtime as one logical Controller.

Example:

```text
Owner ─┐
       ├── Mixer Controller → mobility Lease
AI ────┘
```

Twin Runtime does not define the internal blending algorithm.

---

## 10. Lease Lifecycle

A Control Lease has the following conceptual lifecycle:

```text
ISSUED
  │
  ▼
ACTIVE
  │
  ├── renew ──────────┐
  │                   │
  ├── revoke ─────→ REVOKED
  │
  ├── timeout ─────→ EXPIRED
  │
  └── session end ─→ TERMINATED
```

The final state names may change in the implementation specification.

The important behaviour is normative:

- revoked Lease no longer authorizes actions,
- expired Lease no longer authorizes actions,
- terminated Session invalidates associated Leases.

---

## 11. Lease Renewal

A Lease may be renewed before expiration.

Renewal must:

- preserve or replace the existing authority explicitly,
- generate an audit event,
- not allow ambiguity about the currently active Lease.

The implementation must prevent an older Lease version from becoming authoritative again after renewal or replacement.

---

## 12. Lease Revocation

A Lease may be revoked before its normal expiration.

Revocation must:

- invalidate new commands associated with that Lease,
- trigger the configured Fallback Policy,
- generate an audit event.

Transport connectivity must not override revocation.

A Controller may remain connected but must lose authority.

---

## 13. Lease Expiration

Expiration is based on Runtime authority, not transport lifetime.

Therefore:

```text
connected ≠ authorized
```

If a WebRTC, ROS, DDS, TCP or other connection remains active after Lease expiration, commands must still be rejected.

---

## 14. Liveness

A Lease may require liveness.

Examples may include:

- heartbeat,
- controller state update,
- transport-level health,
- application-level acknowledgement.

The exact mechanism is not defined in this RFC.

Important distinction:

> Liveness proves that a technical control path is alive.

It does not prove:

- human attention,
- human consciousness,
- physical human presence.

---

## 15. Handover

Handover transfers a Control Domain from one Controller to another.

Conceptually:

```text
Before:

conversation → AI

Handover:

AI Lease revoked / replaced
Owner Lease activated

After:

conversation → Owner
```

The Runtime must guarantee that after successful handover:

- previous controller commands are no longer authoritative,
- delayed stale commands cannot regain control,
- the new Controller is identifiable,
- the handover is auditable.

---

## 16. Stale Command Protection

A critical requirement is preventing delayed commands from a previous Controller from affecting the new control state.

Conceptually:

```text
AI controls mobility
      │
      ▼
Owner takes mobility
      │
      ▼
old delayed AI command arrives
      │
      ▼
REJECT
```

The implementation must provide sufficient context to distinguish current authority from stale authority.

Possible mechanisms may later include:

- Lease identifiers,
- generations,
- monotonic sequence numbers,
- epochs,
- equivalent mechanisms.

This RFC does not select one yet.

---

## 17. Presence Modes and Leases

Presence Mode describes the semantic participation model.

Control Leases describe actual technical authority.

They are related but not identical.

---

## 18. Autonomous Mode

Typical conceptual state:

```text
Presence Mode: Autonomous

conversation → AI
gesture      → AI
mobility     → AI
navigation   → AI
```

The specific domains depend on the integration.

AI authority is valid only when:

- Representation Grant permits Autonomous mode,
- Session policy permits it,
- Compliance Policy permits it,
- required Control Leases are valid.

---

## 19. Bridge Mode

Example:

```text
Presence Mode: Bridge

conversation → Owner
gaze         → Owner
gesture      → Owner

mobility     → AI
navigation   → AI
```

Bridge is therefore primarily a Lease allocation and handover model.

The Owner may take control of selected domains without taking control of the whole Twin.

---

## 20. Bridge Takeover

Example sequence:

```text
1. AI controls conversation.
2. Owner observes Session.
3. Owner requests takeover.
4. Runtime validates authorization.
5. AI conversation Lease is revoked/replaced.
6. Owner conversation Lease becomes active.
7. Audit records handover.
```

The same mechanism may apply to:

- gesture,
- gaze,
- mobility,
- other Control Domains.

---

## 21. TotalMersion

During TotalMersion, the Identity Owner must hold the relevant high-level presence-control authority.

Example:

```text
conversation → Owner
voice        → Owner
gaze         → Owner
gesture      → Owner
mobility     → Owner
```

Navigation assistance or OEM local safety may remain autonomous without changing the Presence Mode, provided they do not independently represent the Owner.

---

## 22. TotalMersion Loss

If Owner control is lost:

```text
TotalMersion
     │
     ▼
Owner unavailable
```

Runtime must not silently continue as TotalMersion.

It must execute an explicit transition such as:

```text
TotalMersion → Standby
```

or, if authorized:

```text
TotalMersion → Autonomous
```

The transition must be audited.

---

## 23. Authorized Autonomous Fallback

Autonomous fallback requires all required conditions.

Conceptually:

```text
Representation Grant allows Autonomous
AND
Session Policy allows Autonomous fallback
AND
Compliance Policy allows Autonomous
```

Only then may:

```text
TotalMersion → Autonomous
```

occur automatically.

Otherwise the configured non-autonomous fallback must apply.

---

## 24. Session Lifecycle

A Session has a conceptual lifecycle:

```text
CREATED
   │
   ▼
READY
   │
   ▼
ACTIVE
   │
   ├── presence transitions
   ├── lease handovers
   ├── fallback events
   │
   ▼
ENDED
```

The exact state names are not fixed by this RFC.

A Session must have an unambiguous terminal condition.

Ending a Session invalidates its active Control Leases.

---

## 25. Session Isolation

Sessions must be logically isolated.

A Controller authorized in one Session must not automatically receive authority in another Session.

Example:

```text
Owner:
  Session Tokyo
  Session London

AI controller authorized in Tokyo
≠
AI controller authorized in London
```

Separate Session authority must be maintained.

---

## 26. MultiPresence

One Identity Owner may participate through multiple simultaneous Sessions.

Example:

```text
Identity Owner
 ├── Tokyo Session
 ├── London Session
 └── New York Session
```

Each Session has independent:

- Presence Mode,
- Representation context,
- Control Leases,
- controllers,
- audit events,
- Compliance Policy.

No global Control Lease exists across all Sessions in v0.1.

---

## 27. Deployment Relationship

Where applicable:

```text
Deployment
 ├── Session A
 ├── Session B
 └── Session C
```

A Deployment may outlive a Session.

For example:

```text
humanoid arrives
Session 1
standby
charging
Session 2
humanoid leaves
```

Control Leases remain Session-scoped.

---

## 28. Compliance Interaction

Compliance Policy may further restrict Lease issuance or action execution.

Example:

```text
Representation Grant: allows recording
Control Lease: valid
Compliance Policy: recording prohibited here

Result: recording must not proceed
```

Lease authority cannot override Compliance Policy.

---

## 29. Edge Enforcement Interaction

The Edge Enforcement Agent must evaluate current Runtime authority before allowing a protected action.

Conceptually:

```text
command
  │
  ▼
identify Session
  │
  ▼
identify Controller
  │
  ▼
identify Control Domain
  │
  ▼
validate Lease
  │
  ▼
validate Runtime policy
  │
  ▼
ACCEPT / REJECT
```

Local OEM safety remains the final physical authority after Runtime acceptance.

---

## 30. Audit Requirements

The Runtime must emit audit events for at least:

```text
Session created
Session ended

Representation Grant activated
Representation Grant revoked

Lease issued
Lease renewed
Lease revoked
Lease expired

Controller handover

Presence Mode transition

Fallback triggered

Command rejected because authority was invalid
```

---

## 31. Reference Example: Autonomous to Bridge

Initial state:

```text
Presence Mode: Autonomous

conversation → AI
gesture      → AI
mobility     → AI
navigation   → AI
```

Owner joins.

Runtime does not automatically change authority.

Owner requests conversation takeover.

After validation:

```text
Presence Mode: Bridge

conversation → Owner
gesture      → AI
mobility     → AI
navigation   → AI
```

Owner later takes gesture:

```text
conversation → Owner
gesture      → Owner
mobility     → AI
navigation   → AI
```

Each handover is independent and auditable.

---

## 32. Reference Example: TotalMersion Break

Initial state:

```text
Presence Mode: TotalMersion

conversation → Owner
gaze         → Owner
gesture      → Owner
mobility     → Owner
```

Owner requests a 10-minute break.

Representation Grant permits Autonomous representation.

Session Policy permits Autonomous fallback.

Runtime transitions:

```text
TotalMersion
     ↓
Autonomous
```

New AI Leases are explicitly issued.

The Session is no longer described as TotalMersion.

When Owner returns:

```text
Autonomous
     ↓
TotalMersion
```

AI Leases are revoked or replaced by Owner Leases.

---

## 33. Reference Example: Unauthorized Stale Command

```text
Lease L1:
mobility → AI

Owner takeover

L1 revoked

Lease L2:
mobility → Owner

Delayed command arrives with L1

Result:
REJECT
Audit:
stale_or_revoked_authority
```

This behaviour is required regardless of whether the transport connection used by the AI remains active.

---

## 34. Architectural Invariants

This RFC establishes the following invariants:

1. **Identity Owner is not automatically the Controller.**
2. **Representation Grant and Control Lease are separate.**
3. **Representation Grant does not automatically create control authority.**
4. **Control authority is Session-scoped.**
5. **Control authority is Control-Domain-scoped.**
6. **One active Controller exists per Control Domain.**
7. **Transport connectivity does not equal authority.**
8. **Revoked or expired Leases cannot authorize new commands.**
9. **Stale previous-controller commands cannot regain control.**
10. **Presence Mode transitions are explicit.**
11. **TotalMersion cannot silently become Autonomous.**
12. **Ending a Session terminates its control authority.**
13. **Multiple Sessions belonging to the same Identity Owner remain independently authorized.**
14. **Compliance Policy can further restrict otherwise valid authority.**
15. **Local OEM safety remains above Runtime control authority.**

---

## 35. Open Decisions

The following items are intentionally not decided in RFC-0001:

### Identifier format

Examples:

- UUID,
- URI,
- DID,
- another opaque identifier.

### Representation Grant serialization

Possible future options include:

- Runtime-native JSON,
- W3C Verifiable Credential profile,
- another signed authorization format.

### Lease serialization

Exact wire representation remains undecided.

### Lease timing

Not yet defined:

- default duration,
- renewal window,
- heartbeat interval,
- expiration tolerance.

### Stale-command mechanism

Not yet selected:

- lease generation,
- sequence number,
- epoch,
- equivalent mechanism.

### Atomic multi-domain handover

Not yet decided whether several Control Domains can be transferred atomically as one operation.

### Human presence verification

TotalMersion requires the Identity Owner to be live, but v0.1 does not yet define how the system distinguishes:

- connected,
- active,
- attentive,
- physically present.

### Representation Grant trust model

Not yet defined:

- trusted issuer configuration,
- signatures,
- revocation transport,
- federation.

These decisions require separate RFCs or implementation specifications.

---

## 36. Proposed Decision

Adopt the following conceptual model for Twin Runtime v0.1:

> **A Session represents an Identity Owner under a valid Representation Grant. Controllers receive temporary authority through scoped Control Leases. Each Control Domain has at most one active Controller, and authority changes are explicit, revocable and auditable.**

This model becomes the foundation for subsequent schemas, APIs, Edge Enforcement and conformance tests.
