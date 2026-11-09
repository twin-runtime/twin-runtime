# RFC-0003: Command Authorization, Lease Fencing, Grant Binding and Session Interruption

**Status:** PROPOSED - COMMIT CANDIDATE, pending repository owner approval  
**Target:** Twin Runtime v0.1  
**Date:** 2026-11-09  
**History:** Consolidates the local RFC-0003 review drafts; this document is the single proposed normative baseline.  
**References:** `RUNTIME_REQUIREMENTS.md`, `ARCHITECTURE.md`, `RFC-0001`, `RFC-0002`  
**Boundary:** The Runtime remains provider-neutral and independent of Twin.rent Marketplace. No robot low-level safety or emergency-stop implementation is introduced.

## 1. Decision summary (proposed)

1. Every protected command has a validated `CommandEnvelope`; Edge authenticates its origin and fences stale authority.
2. A v0.1 Control Lease depends on exactly one `representation_grant_id`, but a Grant is not itself controller authorization.
3. The Session Policy explicitly authorizes individual Controllers by Presence Mode and Control Domain. The identity of an authenticated sender must match a permitted Controller.
4. A v0.1 Grant must expose machine-interpretable representation scopes needed for the requested Lease. Unknown authorization-relevant restrictions fail closed.
5. A Session can become `suspended`, with `presence_mode: null`; `standby` remains an Operational State. Autonomous fallback uses newly issued Leases.
6. Owner liveness loss is enforced locally at Edge using configured monotonic deadlines. Bridge as well as TotalMersion has an explicit loss path.
7. The Edge boot epoch (`edge_boot_id`) is authenticated and is part of its installed authority; Edge starts fail-closed after every restart. Within one boot, Edge rejects stale installations with monotonically ordered generation and installation sequence.
8. Every Presence Mode transition and every effective Session Policy or Compliance Policy version change fences all Leases of the Session in v0.1.
9. Core performs issuance-time authorization; Edge independently enforces the installed, bounded authority and local OEM veto.
10. Structural schema checks are not substitutes for cross-record authorization, durable fencing, transport authentication, or Core/Edge conformance tests.

## 2. CommandEnvelope and authenticated control

Normative v0.1 command fields:

```text
command_id                required opaque identifier
session_id                required
controller_id             required, never trusted by itself
control_domain            required
lease_id                  required
lease_generation          required nonnegative integer
issued_at                 required RFC 3339 timestamp, audit only
payload OR payload_reference  exactly one, integration-specific
```

An authenticated transport association or trusted mapping determines the actual Controller identity. The Edge MUST reject a mismatch between that identity and the declared `controller_id`; mere knowledge of a valid `lease_id` does not convey authority.

**Core is the authority issuer.** Before issuing or renewing a Lease, and on each relevant policy/Grant/Session change, Core MUST resolve and verify the authenticated Controller, active Session, selected Presence Mode, supported integration Control Domain and capability, trusted active Grant, applicable versioned Session Policy and Compliance Policy, and validity bounds. A policy or Grant that cannot be resolved or safely evaluated MUST deny authorization. Core MUST NOT delegate these external-policy decisions to an offline Edge.

**Edge is the execution gate.** Edge MUST accept an authenticated authority installation from Core only for its current boot epoch. Immediately before passing a command to the OEM interface, Edge MUST verify the authenticated sender/controller mapping, installed `(session_id, control_domain, lease_id, generation)`, applicable local expiry/liveness deadlines, duplicate command protection, declared integration capability and any explicitly installed local restrictions. The OEM controller/safety layer retains an independent final physical-execution veto. Edge MUST NOT infer legal authorization from a structurally valid command or take over Core policy interpretation.

A command timestamp from the sender MUST NOT be used as proof of freshness. The Edge MUST fail closed when the freshness of its authority view cannot be established.

## 3. Grant binding, scope, and trust

Each v0.1 `ControlLease` MUST contain exactly one `representation_grant_id`. It MUST reference a Grant already associated with the Session. A Lease MUST NOT outlive its supporting Grant.

`Session` MUST bind to the represented entity with `representation_subject_id` before entering `ready` or `active`. `RepresentationGrant.authorized_subject` MUST identify that representation subject, **not** the Controller. No implicit substitution or delegation between these roles is allowed.

For the v0.1 reference implementation, define at least these machine-interpretable technical Grant constraints:

```text
owner_id
provider_id
status
valid_from, valid_until
authorized_subject
allowed_presence_modes[]
allowed_control_domains[]  # proposed required technical scope for Lease issuance
```

`allowed_control_domains` describes the *representation scope* permitted by the Grant, not who may control the domain. The Session Policy determines permitted Controllers. Runtime checks the intersection of valid Grant, Session Policy, Presence Mode, external Compliance Policy, supported capabilities and Lease.

Unknown keys in authorization-relevant `restrictions` MUST block Lease issuance unless the Core has an explicit validator for their semantics. Non-authoritative `extensions` MAY be retained or ignored but MUST NOT override the above rules. The reference v0.1 schema MUST use a closed vocabulary for enforceable authorization restrictions. No claim about the legal sufficiency of underlying consent is implied by this technical check.

**v0.1 trust boundary:** the reference Core accepts Grants provisioned by its configured trusted local administrator, or by an administrator-configured trusted provider with an explicit validation mapping. An arbitrary client-provided Grant is NOT trusted merely because it passes JSON Schema. The reference implementation MAY initially support only trusted local provisioning; third-party federation, signed credentials and external trust discovery are deferred.

Any change to security-relevant Grant authority (scope, status, time, represented subject, issuer binding, version) MUST invalidate affected active Leases. Reissue requires a new `lease_id` and strictly greater generation. Cosmetic metadata changes need not trigger a reissue, but MUST NOT affect authorization.

## 4. SessionPolicy and Controller authorization

`SessionPolicy` MUST use an explicit version and an active/inactive status vocabulary. It MUST define Controller authorization scopes for issued Leases, e.g.:

```json
{
  "controller_authorizations": [
    {
      "controller_id": "controller_owner",
      "allowed_presence_modes": ["bridge", "totalmersion"],
      "allowed_control_domains": ["conversation", "gesture"]
    },
    {
      "controller_id": "controller_agent",
      "allowed_presence_modes": ["autonomous", "bridge"],
      "allowed_control_domains": ["conversation", "gesture"]
    }
  ]
}
```

The example is a **proposal for a new schema field**, not a claim that it already exists. An absent, unparseable, or non-matching Controller authorization MUST deny Lease issue; no implicit permission exists for the Identity Owner, AI, teleoperator, or session participant.

An authenticated Controller MUST match a policy entry for both the currently applicable Presence Mode and the requested Control Domain. For v0.1, **every new effective Session Policy version or Compliance Policy version, or a change in their active/inactive status, MUST invalidate all active Leases of that Session**, regardless of whether the new version appears more permissive. Core MUST not compare policy contents to preserve Leases. Each newly issued Lease obtains a fresh `lease_id` and a greater generation for its Session + Control Domain. Policy versions must identify immutable effective content; do not silently rewrite a version in place. Compliance Policy is separately resolved and versioned; its absence or inability to evaluate a required restriction MUST fail closed.

`Session` MAY be created without resolved policies. Before `ready` or `active`, it MUST have resolvable, valid references including IDs and versions of Session Policy and Compliance Policy, plus a resolved representation subject and applicable Grant. Leases may be issued only while `session_status = active`.

## 5. Lease fencing, revocation and deduplication

For each `(session_id, control_domain)`, Core MUST maintain a durable, monotonically increasing `generation` (or an equivalent persistent epoch) for each new authority assignment and each revocation/invalidation. An ordinary extension of a still-valid Lease by the same Controller does not increase generation, but MUST increase `installation_sequence` for that generation. A previously invalidated generation MUST never become authoritative, including after Core or Edge restart.

Edge MUST accept commands only when `(session_id, control_domain, lease_id, lease_generation, authenticated_controller)` matches its currently installed effective authority and the local validity deadline has not passed. Core MUST atomically fence and replace authority within its own transaction boundary; it MUST NOT claim an atomic transaction with an offline Edge.

For the v0.1 reference implementation, revocation/expiry/policy changes MUST invalidate affected authority immediately at Core, publish an update, and create correlated audit events. A disconnected Edge cannot know about remote revocation instantaneously. Therefore Edge MUST also enforce locally installed, bounded Lease validity and a separate liveness deadline based on its monotonic clock; lack of a trustworthy refreshed authority view results in fail-closed after the configured bound. The system MUST NOT advertise zero-delay global revocation.

`command_id` is mandatory. For non-idempotent commands, the active Edge MUST reject duplicate command IDs for the *entire effective life of that Lease*, including renewals, not merely for one original TTL. Old Lease commands are rejected once that Lease is replaced or ended. The v0.1 reference implementation MAY keep an in-memory deduplication set while a Lease is live, provided all Leases are invalidated safely across Edge restart and replacement. Production-scale streaming and memory-bounded deduplication require a separate design; do not weaken safety by silently expiring the deduplication record while the same Lease remains authoritative.

### 5.1 Edge boot epoch and safe reattachment

Each authenticated Edge installation has a stable `edge_id` and a fresh, non-reused `edge_boot_id` for each process/device restart. On startup the Edge MUST **reject all protected commands and cached authority installations** until it registers its current boot epoch with Core over an authenticated connection and receives an authority installation explicitly bound to that same epoch. Old installation messages from a previous boot MUST be rejected, even if delivered late. An Edge MUST NOT resume from an old local Lease cache.

Core MUST record the authenticated `edge_id` / `edge_boot_id` relationship and associate installed authorities with the Edge. On a changed `edge_boot_id`, Core MUST invalidate every active Lease bound to that Edge (across affected Sessions and Control Domains), advance the durable generation for each affected pair, audit the reason and issue entirely new Leases **only after** revalidating Grant, policies, Controller, Presence Mode and current Session state. Reinstallation MUST include the new `lease_id`, higher `generation`, current `edge_boot_id` and a bounded validity time. A fresh `edge_boot_id` is not proof of robot or controller identity by itself; it is accepted only from an authenticated Edge.

A new Edge boot during `totalmersion` or `bridge` while a human holds any applicable Lease MUST be treated as loss of live human control, not an automatic transparent reconnection. Core MUST first suspend the Session or perform an expressly permitted fallback according to Section 6, before any new Owner Lease can be issued. Returning the Owner to active live control requires explicit authenticated Session resumption, revalidation and fresh Leases with higher generations. Edge restart MUST NOT silently revive the previous Presence Mode. Other sessions/domains affected by the boot also lose their old authorities.

If Core is unavailable during startup, the Edge MUST remain fail-closed for protected commands. If Core restarts, durable fencing values and authority state MUST not roll back; reconnect must revalidate the Edge installation. This does not imply instantaneous remote revocation while a previously connected Edge is disconnected: its local, bounded TTL/liveness enforcement remains the last guaranteed limit.

### 5.1.1 Ordered authority installation within one Edge boot

The public Edge-Core contract in `spec/v0.1/edge-authority.schema.json` defines three messages: `edge.register`, `edge.authority_install` and `edge.authority_revoke`. The schema validates shape; transport authentication and monotonic ordering require executable logic.

For every `(session_id, control_domain)` in its current boot, Edge MUST retain the highest accepted `generation`, and, within that generation, the highest accepted `installation_sequence`. An authenticated authority-installation or revocation message with a lower pair MUST be rejected. An equal pair MUST NOT replace existing state. **Revocation MUST advance `generation`** and install a tombstone: the revoked generation MUST NOT authorize new installation even if a later message has a higher sequence for that same generation. A future Lease requires a strictly higher generation.

Renewal of one valid Lease MAY keep its generation but MUST increase `installation_sequence`; a same-generation update MUST NOT change `lease_id` or `controller_id`. Edge MUST independently enforce the installed absolute expiry and local monotonic TTL bounds. A delayed installation MUST NOT extend authority past the trusted Core-issued `lease_valid_until`; if Edge cannot establish the trusted expiry bound, it MUST fail closed. A new Controller, Lease replacement, policy change or revocation MUST use a higher generation. These counters are issued by Core, not by clients or unauthenticated transports. Edge MUST bind all accepted updates to the authenticated Core and its current `edge_boot_id`.

The reference implementation MAY store this watermark in memory for the current Edge boot **only if** boot reattachment guarantees that all preceding Leases are invalidated at Core and a new, higher generation is issued before any command is accepted. Otherwise durable fencing storage is required.

### 5.2 Presence Mode transitions

For v0.1, **every change of effective `presence_mode` MUST invalidate all active Session Leases** before new mode-specific authority is issued. Invalidation advances each affected Session + Control Domain generation; no Lease from the previous mode is carried forward. Core MUST check whether the new mode is permitted by the current Grant, Session Policy and Compliance Policy. If requirements are not satisfied, fail closed and suspend or enter another explicitly declared non-representing state.

This conservative rule intentionally avoids partial mode-diff logic. In the special case of an authorized fallback to `autonomous`, Core MUST issue fresh Leases to a policy-authorized AI Controller; it cannot transfer an existing Owner Lease. Edge may continue to hold stale, bounded authority while disconnected, so live revocation must follow the v0.1 TTL/liveness caveat above.

### 5.3 Integration capability gate and timeouts

An integration MUST declare the Control Domains it actually supports using an authenticated configuration/adapter registration. Unknown or undeclared domains MUST fail Lease issuance at Core and command execution at Edge; a syntactically valid domain string alone is insufficient. Unknown capability state is not equivalent to supported.

Every issued Lease requires a configured finite local validity bound. For any mode requiring live human control (Bridge when a human controls a domain, and TotalMersion), a locally enforceable authenticated liveness source and finite timeout MUST be configured **before activating that mode**. Missing, unsupported or invalid timeout configuration MUST block activation (fail closed). There is no assumed universal numeric timeout without transport/integration measurements.


## 6. Session lifecycle and Presence Mode

`session_status` MUST be one of:

```text
created | ready | active | suspended | ended
```

`presence_mode` MUST be one of `autonomous | bridge | totalmersion` when `session_status = active`. For **all non-active statuses** (`created`, `ready`, `suspended`, `ended`) `presence_mode` MUST be `null`. The field is always present. This avoids stale mode labels during suspension and clarifies that a ready Session is not yet representing the Owner.

`operational_state` remains a separate, extensible string such as `standby`, `ready`, `degraded` or `unavailable`, and MUST NOT be interpreted as Presence Mode. `standby` is a typical operational state of a suspended physical Twin, not the name of a mode.

### 6.1 TotalMersion liveness loss

The Edge detects loss of the Owner's live control via configured, locally measured heartbeat/authenticated control liveness deadlines using a monotonic clock. A technical heartbeat demonstrates connectivity, not human attention. Each supported integration MUST document the liveness source and timeout; the RFC does not invent a universal numerical timeout.

On loss, the Edge MUST stop accepting the affected Owner commands and execute the permitted local fallback hook. Core MUST audit the loss and, when it receives or independently establishes it, perform one explicit transition:

- **Default:** revoke/fence dependent Leases and transition to `suspended`, `presence_mode: null`, with an appropriate nonrepresenting Operational State.
- **Autonomous fallback:** permitted only if the active Grant includes `autonomous`, the effective Session Policy and Compliance Policy allow fallback, and a separately authenticated and policy-authorized autonomous Controller receives a **new Lease with a new generation**. The Owner's Lease is never silently inherited.

If Core is temporarily unreachable, Edge stops unsafe actions locally according to its bounds even though Core's last synchronized Session snapshot may still show `totalmersion`. The public/UI status MUST NOT claim confirmed live Owner control without current evidence.

### 6.2 Bridge loss

When the Owner loses authenticated control during `bridge`, Edge MUST fence Owner-controlled domains and invoke only their declared, locally permitted fallback. For v0.1 there are three explicit outcomes:

1. **Suspend (default):** `session_status: suspended`, `presence_mode: null`; no active protected Leases.
2. **Autonomous fallback:** an explicit mode transition, allowed by the active Grant and both policies, followed by newly issued policy-authorized AI Leases with higher generations.
3. **Continue Bridge (narrow exception):** only when **another authenticated human Controller already holds a valid Lease** in the Session for an applicable human-controlled domain, and the Grant and both policies permit that Controller and continued Bridge representation. Core records this determination and fences the lost Owner's affected domains. Those domains MAY remain without an active Controller; they MUST NOT be transferred implicitly to an AI or another human. Mere network connectivity or an observer participant does not satisfy this condition.

If none of these paths can be validated, suspend. No Owner Lease is inherited, and no other controller gains authority solely due to loss of the Owner.

Both loss paths MUST produce correlated events for authority loss, revoked/expired Leases, fallback, and any Session status or Presence Mode change.

## 7. Required audit context

For `lease.*`, `command.rejected`, Edge boot/re-attachment, policy-version changes and mode-transition events, the Runtime **MUST** produce a structured, correlatable audit record. When ascertainable, it MUST include `session_id`, `control_domain`, `lease_id`, `controller_id`, `grant_id`, effective Session Policy ID/version, effective Compliance Policy ID/version, fencing `generation`, `correlation_id`, outcome and a machine-readable rejection/invalidation reason. It MUST NOT fabricate an identifier for malformed, untrusted or missing input (e.g. a rejected command with no valid `lease_id`); such cases MUST still be recorded with the reliably observed information.

Core assigns `session_sequence` to recorded Session-scoped events. Edge-originated events while disconnected may use separate `edge_id`, `edge_boot_id`, and locally ordered event metadata until Core ingests and assigns Session ordering; Edge MUST NOT invent authoritative Core sequence values. Preserve correlation when reconnected; do not claim real-time global audit ordering across disconnected Edge nodes. Sensitive legal, biometric or raw command data remain outside audit events.

New/clarified event types required for the reference implementation include `session.suspended`, `session.resumed`, `edge.boot_registered`, `edge.authority_invalidated` and `edge.authority_installed`, as well as existing `lease.*`, `presence_mode.changed`, `session_policy.changed`, `compliance_policy.changed`, `fallback.triggered`, and `command.rejected`.

## 8. Schema amendments and conformance tests

**Follow-up schema updates required before Core:**

- `representation-grant.schema.json`: enforce validated domain scope and restriction keys for v0.1; reject unknown security-bearing restrictions.
- `session.schema.json`: add `representation_subject_id`, mandatory `session_status`, policy IDs and versions; make `presence_mode` null iff status is non-active; require resolvable refs for `ready`/`active`. `operational_state` is **already present** and remains separate.
- `session-policy.schema.json`: versioned Controller authorization matrix with mode/domain scope and fixed status values.
- `control-lease.schema.json`: one required `representation_grant_id`.
- `command-envelope.schema.json`: new protected command structure.
- `runtime-event.schema.json`: add event forms, machine-readable reasons, Edge boot/re-attachment context and effective authority references/versions needed to reconstruct decisions; do not require a fabricated Lease ID for malformed commands.
- `CompliancePolicyRef` (minimal normalized reference, not a legal policy engine): record effective policy ID, version and resolvable status; do not introduce a full regulatory rule language in v0.1.
- **Public `edge-authority.schema.json` contract:** authenticated `edge_id`, fresh `edge_boot_id`, bound current Lease/generation, strictly ordered `installation_sequence` and finite validity. Core and Edge MUST validate the contract and enforce ordering in code. The schema alone cannot enforce stateful fencing.
- `common.schema.json`: shared formats and closed authorization enums where applicable.
- Dependency lock or pinned requirements for full Draft 2020-12 validation including RFC 3339 format support, independent schema/unit tests and negative fixtures.

**Core/Edge conformance tests (not expressible by JSON Schema alone):**

1. Valid Grant but Controller absent from Session Policy -> deny Lease.
2. Authenticated sender differs from command-declared controller -> reject.
3. Grant and Lease exist but requested Control Domain is not in Grant scope -> deny.
4. Unknown enforceable Grant restriction -> fail closed.
5. Security-relevant Grant authority change -> exactly the dependent Leases invalidated; unrelated Grant-dependent Leases preserved unless another rule requires revocation.
6. New effective Session Policy or Compliance Policy version -> **all** Session Leases invalidated, regardless of Grant, and generation advances.
7. AI to Owner handover -> delayed old-generation command rejected.
8. TotalMersion loss -> Edge local halt/fallback; Session suspends or enters explicitly authorized Autonomous with fresh Lease.
9. Bridge Owner loss -> affected domains fenced; suspend or enter Autonomous with fresh Leases, unless another already-leased authenticated human Controller permits explicit Bridge continuation.
10. No/invalid versioned policies -> deny readiness and Lease issue.
11. Duplicate command ID -> reject throughout the effective Lease lifetime, including renewals.
12. Core restart -> no reuse of a previously invalidated authority generation.
13. MultiPresence -> grants, policies, Leases and events remain session-isolated. The same authenticated Controller MAY hold Leases in two Sessions **only if independently authorized in each**; no cross-Session authority is implied.
14. Edge restarts, announces a new `edge_boot_id`, and an old command or authority installation is replayed -> reject; only new Lease IDs/generations installed for the new boot can authorize commands.
15. Presence Mode changes (e.g. `bridge` to `totalmersion`) -> all old Session Leases are fenced; old commands are rejected; every new Lease has a greater domain generation.
16. Unsupported Control Domain or missing configured live-human timeout -> deny Lease issuance or mode activation, even if JSON Schema accepts the domain string.
17. Late `edge.authority_install` or renewal for lower `(generation, installation_sequence)` arrives after a higher-generation revocation in the same Edge boot -> reject; the tombstone remains authoritative.
18. An Edge restart during `totalmersion` or human-controlled `bridge` -> Session suspends or performs expressly authorized fallback; no silent Owner Lease reinstall or unverified restoration of live Presence Mode.
19. Edge installation for the same generation but a different `lease_id` or `controller_id` -> reject, including if `installation_sequence` increased; generation must advance for a replacement.

**Testing boundary:** a passing JSON Schema test proves syntactic validity, not live safety, legal authorization, cryptographic integrity, robot physical safety, or correctness of connected OEM hardware.

## 9. Deferred beyond v0.1

Signed credentials, federated issuer trust, legal interpretation of licensing, biometric matching, verification of actual human attention, atomic multi-domain handover, universal safety certification, high-rate motion-stream deduplication, production-grade offline revocation guarantees, and provider-specific SDK integrations are not part of this RFC.

## 10. Approval and change control

This is a **commit candidate pending explicit repository owner approval**, not an implemented or released specification. Before full Core implementation, reconcile accepted rules into RFC-0001, RFC-0002 and `RUNTIME_REQUIREMENTS.md`, and update the remaining schemas and tests. The attached Edge contract and isolated reference fence tests do not implement complete Core/Edge authorization. Do not publish or change GitHub without the repository owner's explicit authorization. No commercial Marketplace strategy or confidential partner information belongs in the public Runtime repository.