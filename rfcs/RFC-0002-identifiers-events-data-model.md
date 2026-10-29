# RFC-0002: Identifiers, Events and Minimal Data Model

**Status:** Draft  
**Target:** Twin Runtime v0.1  
**Related:** `ARCHITECTURE.md`, `RUNTIME_REQUIREMENTS.md`, `RFC-0001`

---

## 1. Summary

This RFC defines the minimal data model required to implement Twin Runtime Core.

It covers:

- identifiers,
- entity references,
- Session state,
- Presence Mode,
- Control Domains,
- Control Leases,
- Representation Grant references,
- Session Policy references,
- Runtime events,
- event ordering,
- audit correlation.

The goal is to create a stable conceptual contract before defining final JSON Schema, APIs or storage.

---

## 2. Goals

Twin Runtime v0.1 needs a data model that is:

- implementation-neutral,
- transport-neutral,
- extensible,
- usable without Twin.rent Marketplace,
- usable without a physical humanoid,
- suitable for conformance testing,
- compatible with future signed credentials,
- compatible with multiple simultaneous Sessions.

---

## 3. Non-Goals

This RFC does not define:

- database technology,
- REST API,
- RPC protocol,
- WebRTC messages,
- ROS messages,
- W3C VC profile,
- cryptographic signatures,
- KYC data,
- Marketplace entities,
- billing,
- legal contract format.

---

# 4. Identifier Principle

All core Twin Runtime entities must have stable identifiers.

v0.1 should treat identifiers as **opaque strings**.

Example:

```text
owner_01HZX...
session_01HZY...
lease_01HZZ...
grant_01HZA...
```

Applications must not derive authorization decisions from identifier structure.

---

## 5. Identifier Requirements

The following entities MUST have unique identifiers:

- Identity Owner
- Representation Provider
- Representation Grant
- Deployment
- Session
- Participant
- Controller
- Control Lease
- Session Policy instance
- Compliance Policy instance
- Runtime Event

Identifiers:

- MUST be treated as opaque values,
- MUST remain stable for the lifetime of the entity,
- MUST NOT contain secrets,
- SHOULD be globally unique where practical.

---

## 6. Identifier Format

RFC-0002 does not mandate UUID, ULID, DID or URI.

The reference implementation SHOULD use a sortable opaque identifier format.

Recommended working default:

```text
<prefix>_<opaque-id>
```

Examples:

```text
owner_...
provider_...
grant_...
deployment_...
session_...
participant_...
controller_...
lease_...
session_policy_...
compliance_policy_...
event_...
```

Prefixes are for readability only.

Authorization MUST NOT depend on them.

---

# 7. Entity References

Entities should reference each other by identifier rather than embedding full objects unnecessarily.

Example:

```text
ControlLease
    lease_id
    session_id
    controller_id
    control_domain
```

This avoids coupling storage layout to the Runtime model.

---

# 8. Identity Owner

Minimal conceptual record:

```text
IdentityOwner
    owner_id
    display_name? 
    metadata?
```

Only `owner_id` is required by Runtime Core.

Commercial KYC and identity-verification data remain outside Runtime Core.

---

# 9. Representation Provider

Minimal record:

```text
RepresentationProvider
    provider_id
    type
    metadata?
```

Possible types may include:

```text
self_hosted
twin_rent
external
test
```

The type list is not normative in v0.1.

---

# 10. Representation Grant Reference

Twin Runtime Core requires a normalized representation-authority view.

Conceptually:

```text
RepresentationGrantRef
    grant_id
    provider_id
    owner_id
    authorized_subject
    valid_from
    valid_until
    allowed_presence_modes[]
    status
    restrictions?
    authorization_reference?
    authorization_version?
```

Runtime Core may receive this from:

- a native object,
- a signed credential,
- a Marketplace backend,
- another authorization provider.

The original external credential may remain outside Runtime Core.

Where a Representation Grant is derived from an external consent, authorization or policy artifact, Runtime SHOULD retain a stable reference and version sufficient to identify which authorization state was in force.

Runtime Core does not define the legal meaning or storage format of that external artifact.

---

# 11. Grant Status

Minimum normalized states:

```text
active
revoked
expired
invalid
```

The reference implementation MAY include:

```text
pending
suspended
```

but they are not required for v0.1.

Only an `active` Grant may authorize representation.

---

# 12. Deployment

Minimal Deployment record:

```text
Deployment
    deployment_id
    owner_id
    twin_instance_id?
    location_context?
    started_at?
    ended_at?
    operational_state
    compliance_policy_id?
```

A Deployment may contain zero or more Sessions.

---

# 13. Session

Minimal Session record:

```text
Session
    session_id
    owner_id
    deployment_id?
    presence_mode
    operational_state
    representation_grant_ids[]
    session_policy_id?
    compliance_policy_id?
    created_at
    started_at?
    ended_at?
```

Session state MUST be independently addressable.

---

# 14. Session Policy Reference

Runtime Core SHOULD support a Session Policy reference.

Conceptually:

```text
SessionPolicyRef
    policy_id
    session_id
    version
    status
```

The effective Session-specific restrictions may be normalized separately.

A change of Session Policy version MUST be distinguishable in Runtime state and audit events.

---

# 15. Session Status

The reference model SHOULD distinguish lifecycle status from Operational State.

Suggested Session lifecycle:

```text
created
ready
active
ended
```

This list is intentionally small.

More detailed physical states belong to Operational State.

---

# 16. Presence Mode

Normative Presence Mode values for v0.1:

```text
autonomous
bridge
totalmersion
```

These values should remain stable across integrations.

Unknown future Presence Modes must not be silently interpreted as one of these three.

---

# 17. Operational State

Operational State is extensible.

Reference values may include:

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

Integrations MAY add vendor-specific states.

Vendor-specific values SHOULD be namespaced.

Example:

```text
unitree:protective_stop
booster:custom_mode
```

---

# 18. Participant

A Participant is any entity taking part in a Session.

Minimal record:

```text
Participant
    participant_id
    session_id
    participant_type
    external_identity?
    metadata?
```

Possible `participant_type` values:

```text
identity_owner
human_operator
ai_agent
robot
observer
service
```

The list may be extended.

---

# 19. Controller

A Controller is an entity capable of producing actions for one or more Control Domains.

Minimal record:

```text
Controller
    controller_id
    participant_id?
    controller_type
    external_identity?
```

Possible controller types:

```text
human
ai
policy
mixer
system
```

A Participant may exist without being a Controller.

---

# 20. Control Domain

Control Domain identifiers are strings.

Reference domains:

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

Custom domains SHOULD be namespaced.

Example:

```text
vendor:arm_left
provider:avatar_expression
```

Twin Runtime MUST NOT assume that every integration supports every domain.

---

# 21. Control Lease

Minimal Lease model:

```text
ControlLease
    lease_id
    session_id
    control_domain
    controller_id

    issued_at
    valid_from
    valid_until

    status

    generation
```

`generation` is proposed as the v0.1 mechanism for stale-authority protection.

---

# 22. Lease Generation

Each new authority assignment for a Session + Control Domain SHOULD increment a monotonically increasing generation number.

Example:

```text
conversation

generation 12 → AI
generation 13 → Owner
generation 14 → AI
```

A command associated with generation 12 must not be accepted while generation 13 or 14 is authoritative.

---

# 23. Why Generation Exists

Transport systems may deliver delayed messages.

Therefore:

```text
connection identity alone
```

is insufficient.

A command needs enough context to prove that it belongs to the currently active authority generation.

This protects against:

- delayed commands,
- reconnects,
- previous controllers,
- stale buffers,
- race conditions during handover.

---

# 24. Lease Status

Minimum values:

```text
active
revoked
expired
terminated
```

Only `active` authorizes new actions.

---

# 25. Lease Replacement

When authority changes:

```text
Lease A
    ↓
Lease B
```

Lease B becomes the authoritative Lease for the new generation.

Lease A MUST no longer authorize commands.

The Runtime MAY keep Lease A for audit history.

---

# 26. Command Envelope

RFC-0002 proposes that every protected Runtime action can be normalized into a command context equivalent to:

```text
CommandEnvelope
    command_id
    session_id
    controller_id
    control_domain
    lease_id
    lease_generation
    issued_at
    payload_reference_or_payload
```

Exact serialization is deferred.

---

# 27. Command Identifier

Every protected command SHOULD have a unique `command_id`.

This allows:

- deduplication,
- audit correlation,
- acknowledgement,
- troubleshooting.

---

# 28. Command Payload

Runtime Core must not require all payloads to use one universal format.

Payload may be:

- embedded,
- referenced,
- provided by an integration-specific schema.

Example:

```text
control_domain = "gesture"
payload = integration-specific gesture command
```

Runtime is responsible for authority.

Integration remains responsible for action semantics.

---

# 29. Runtime Event Model

Every significant Runtime state change MUST produce an event.

Minimal conceptual structure:

```text
RuntimeEvent
    event_id
    event_type
    occurred_at

    session_id?
    deployment_id?
    owner_id?

    actor_id?
    controller_id?

    lease_id?
    grant_id?
    session_policy_id?

    control_domain?

    correlation_id?

    data?
```

---

# 30. Event Time

Events MUST contain an `occurred_at` timestamp.

The reference implementation SHOULD use UTC.

Example:

```text
2026-10-28T21:42:12.381Z
```

Runtime MUST NOT assume that clocks from all external devices are perfectly synchronized.

---

# 31. Event Ordering

Wall-clock timestamps alone are not sufficient for ordering security-critical Runtime events.

Each Session SHOULD therefore maintain a monotonic event sequence:

```text
session_sequence
```

Example:

```text
1042 lease.revoked
1043 lease.issued
1044 command.rejected
```

`session_sequence` is authoritative for event order within a Session.

---

# 32. Event Identifier vs Sequence

These have different purposes:

```text
event_id
```

provides global event identity.

```text
session_sequence
```

provides ordering inside one Session.

Both SHOULD be present in Session-scoped Runtime events.

---

# 33. Minimum Event Types

Twin Runtime v0.1 MUST define at least:

```text
deployment.created
deployment.state_changed
deployment.ended

session.created
session.started
session.ended

presence_mode.changed

representation_grant.activated
representation_grant.revoked
representation_grant.expired

session_policy.changed
runtime_control.revoked

lease.issued
lease.renewed
lease.revoked
lease.expired
lease.terminated

control.handover

command.authorized
command.rejected

fallback.triggered
safe_stop.requested

readiness.changed
compliance_policy.changed
```

---

# 34. Optional High-Volume Events

Runtime SHOULD NOT require every successful realtime action to become a persisted audit event.

For high-frequency domains such as:

```text
mobility
gaze
gesture streaming
```

integrations may emit summarized or sampled events.

Security-relevant decisions MUST still be observable.

Examples:

- Lease accepted,
- Lease rejected,
- controller changed,
- stale command rejected.

---

# 35. Event Actor

Where applicable, an event should distinguish:

```text
actor
```

from:

```text
Identity Owner
```

Example:

```text
Identity Owner: owner_paulo
Actor: ai_agent_7
```

The AI may act on behalf of the Identity Owner but is not the Identity Owner.

---

# 36. Event Correlation

Events related to one operation SHOULD share a `correlation_id`.

Example:

```text
takeover requested
lease revoked
new lease issued
presence mode changed
```

may all belong to one takeover operation.

---

# 37. Control Handover Event

A handover event SHOULD identify:

```text
session_id
control_domain

previous_controller_id
previous_lease_id

new_controller_id
new_lease_id

reason
```

This allows reconstruction of control history.

---

# 38. Presence Mode Change Event

A Presence Mode transition event SHOULD contain:

```text
from_mode
to_mode
reason
initiated_by
```

Example:

```text
from: totalmersion
to: autonomous
reason: owner_requested_break
```

---

# 39. Command Rejection Event

A rejection event SHOULD expose a stable machine-readable reason.

Reference reasons:

```text
no_active_lease
lease_expired
lease_revoked
stale_generation
wrong_controller
wrong_session
wrong_control_domain
representation_not_authorized
session_policy_denied
presence_mode_not_allowed
compliance_denied
capability_unavailable
runtime_not_ready
```

The final list may expand.

---

# 40. Sensitive Data

Runtime events SHOULD avoid unnecessary sensitive personal data.

Events SHOULD reference:

```text
owner_id
controller_id
participant_id
```

rather than embedding:

- legal names,
- identity documents,
- biometric data,
- raw conversation content.

Commercial and KYC data remain outside Runtime Core.

---

# 41. Observation Source

Runtime may model available observation streams using:

```text
ObservationSource
    observation_id
    session_id?
    source_id
    modality
    access_policy_reference?
    stream_reference?
    status
```

This object describes the source.

It does not transport the raw stream.

---

# 42. Observation Modalities

Reference modalities may include:

```text
vision.rgb
vision.depth
audio
imu
acceleration
temperature
thermal
proximity
tactile
pressure
force
torque
olfactory
battery
power
joint_state
```

The namespace MUST remain extensible.

---

# 43. Capability Reference

Runtime v0.1 may use capability identifiers without defining a universal capability system.

Example:

```text
CapabilityRef
    capability_id
    provider?
    version?
```

Examples:

```text
speech.output
gesture.wave
mobility.walk
navigation.goto
vision.rgb
```

Capability discovery may later integrate with external systems.

---

# 44. Readiness Snapshot

Reference conceptual model:

```text
ReadinessSnapshot
    readiness_id
    timestamp

    overall_status

    capability_status[]
    energy?
    connectivity?
    thermal?
    integration_health?
```

Possible overall states:

```text
ready
degraded
not_ready
unknown
```

---

# 45. Compliance Policy Reference

Runtime Core SHOULD treat Compliance Policy as an external policy input.

Conceptually:

```text
CompliancePolicyRef
    policy_id
    provider_id?
    version?
    valid_from?
    valid_until?
```

The effective technical restrictions may be normalized separately.

---

# 46. Effective Policy

Runtime may normalize applicable restrictions into an internal structure such as:

```text
EffectivePolicy
    recording_allowed?
    streaming_allowed?
    autonomous_allowed?
    mobility_allowed?
    geofence?
    sensor_restrictions?
    retention_constraints?
    disclosure_requirements?
```

The exact schema is deferred.

---

# 47. State vs Event

Twin Runtime must distinguish:

### State

Current truth.

Example:

```text
conversation controller = Owner
```

### Event

Something that happened.

Example:

```text
conversation transferred from AI to Owner
```

Runtime must not rely only on mutable state for audit reconstruction.

---

# 48. Reference Session Snapshot

A possible normalized snapshot:

```text
SessionSnapshot
    session_id
    owner_id

    presence_mode
    operational_state

    active_grants[]
    active_leases[]

    session_policy_id?

    participants[]
    controllers[]

    compliance_policy_id?
    readiness?

    latest_session_sequence
```

This is conceptual, not yet a wire schema.

---

# 49. Reference Bridge Example

```text
Session:
    session_id: session_tokyo_01
    owner_id: owner_01
    presence_mode: bridge

Active Leases:

    conversation:
        controller: owner_01
        generation: 42

    gesture:
        controller: owner_01
        generation: 18

    mobility:
        controller: ai_07
        generation: 9

    navigation:
        controller: ai_07
        generation: 11
```

This single snapshot describes who currently controls what.

---

# 50. Reference Handover Example

Before:

```text
conversation
generation 42
controller AI
```

Owner takeover:

```text
lease AI revoked
generation 43 created
controller Owner
```

Delayed AI command arrives:

```text
command generation = 42
current generation = 43
```

Result:

```text
REJECT: stale_generation
```

---

# 51. MultiPresence Data Model

Multiple Sessions may reference the same `owner_id`.

Example:

```text
owner_01

session_tokyo
session_london
session_new_york
```

No Session may infer control authority from another Session.

Leases remain isolated by `session_id`.

Runtime MUST support an authorized lookup equivalent to:

```text
active Sessions for owner_id
```

The lookup returns Session references or snapshots and does not imply cross-Session control authority.

---

# 52. Data Model Independence

The model MUST NOT assume:

- relational database,
- document database,
- event store,
- message broker,
- cloud deployment,
- local deployment.

Reference implementation choices remain separate.

---

# 53. Serialization Direction

The likely v0.1 serialization will be JSON-compatible.

However, RFC-0002 does not yet mandate:

- JSON Schema,
- Protobuf,
- MessagePack,
- CBOR,
- another encoding.

Normative schemas will be defined after this RFC is accepted.

---

# 54. Versioning

Normative Runtime objects SHOULD carry or inherit a schema/runtime version.

Example:

```text
runtime_version
schema_version
```

Exact placement remains undecided.

---

# 55. Extensibility

Runtime-defined structures SHOULD support extension without allowing extensions to override core semantics.

Vendor extensions SHOULD use namespaced fields or extension objects.

Example:

```text
extensions:
    unitree:
        ...
```

or equivalent.

---

# 56. Unknown Fields

Future compatible implementations SHOULD tolerate unknown non-critical extension fields.

They MUST NOT silently accept unknown values that alter authorization semantics.

---

# 57. Proposed v0.1 Defaults

RFC-0002 proposes the following implementation defaults:

1. identifiers are opaque strings,
2. reference implementation uses sortable opaque IDs with readable prefixes,
3. timestamps use UTC ISO 8601,
4. Session events use a monotonic `session_sequence`,
5. Control Lease handover uses monotonic `generation`,
6. protected commands reference Lease identity and generation,
7. event payloads minimize personal data,
8. high-volume sensor streams remain outside Runtime Core,
9. core Runtime data is JSON-compatible,
10. Session Policy references are version-identifiable,
11. Representation Grants may retain a stable external authorization reference and version,
12. final JSON Schema is defined separately.

---

# 58. Open Decisions

The following remain open:

### Identifier implementation

ULID vs UUIDv7 vs another format.

### Timestamp precision

Milliseconds vs microseconds vs nanoseconds.

### Event persistence

Append-only file, database, event store or pluggable interface.

### Command deduplication

Whether `command_id` is mandatory for every realtime control message.

### Lease generation scope

Recommended:

```text
Session + Control Domain
```

but this must be confirmed during implementation.

### Event schemas

Whether to use:

- JSON Schema,
- Protobuf,
- both.

### Capability naming

Whether Runtime eventually defines a registry or relies completely on external ecosystems.

### Observation naming

Whether modalities should eventually align with another standard vocabulary.

---

# 59. Proposed Decision

Adopt the following v0.1 model:

> **Twin Runtime uses opaque stable identifiers, version-identifiable policy references, Session-scoped event ordering, Control-Domain-scoped Lease generations and structured Runtime events. High-volume data remains outside Runtime Core, while Runtime maintains authorization, references and auditable state transitions.**

This model becomes the basis for the first normative schemas and Core implementation.
