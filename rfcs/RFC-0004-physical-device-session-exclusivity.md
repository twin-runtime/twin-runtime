# RFC-0004: Exclusive Physical-Device Control Across Sessions

**Status:** Draft  
**Target:** Twin Runtime v0.1  
**Issue:** [#6 - Physical robot Session exclusivity](https://github.com/twin-runtime/twin-runtime/issues/6)  
**Related:** [RFC-0001](RFC-0001-session-representation-control-lease.md), [RFC-0003](RFC-0003-command-lease-grant-session.md), [Architecture](../ARCHITECTURE.md), [Runtime Requirements](../RUNTIME_REQUIREMENTS.md)

---

## 1. Decision summary

**Option A (proposed for v0.1): one physical robot may have at most one effective controlling Session at any instant, across all command Control Domains.** Within that one Session, different Controllers may hold different domain Leases under RFC-0001 and the applicable Session Policy.

This physical-resource invariant is additional to **one active Controller per Control Domain per Session**. A Deployment may contain sequential controlling Sessions. Different devices and independent digital representations may have concurrent Sessions, subject to separate Identity Owner live-presence constraints (C-2).

**DRAFT ONLY:** All MUST/SHOULD language in this RFC specifies *proposed* future requirements, not implemented behavior or an Accepted normative contract. The current Python Core and Edge do not implement device-level exclusivity.

## 2. Observed reference gap

- `reference/runtime_core.py` issues and replaces Leases per `(session_id, control_domain)`.
- `reference/edge_fence.py` records authority per `(session_id, control_domain)`.
- As a result, two different Sessions targeting one `edge_id` may each independently install effective Lease state and pass simulated command checks.
- Existing `edge_boot_id` registration already fences authority after a simulated Edge restart: Core rejects reused boot IDs, discards undelivered messages for previous boots and suspends affected Sessions; Edge rejects messages for another boot.
- Core uses serialized SQLite transactions on one persistent database. It has **no** proven coordination mechanism for multiple independent Core writers.
- Edge ACK is a local, unauthenticated simulation; no OEM stop completion, transport or production physical control is implemented.

This is a **reference authorization-model gap**, not evidence of a physical robot exploit or production system.

## 3. Scope and non-goals

### In scope

- Physical-device resource identity, classification and exclusive controlling Session.
- Authenticated acquire/release permissions, durable slot lifecycle and non-preemptive handover.
- Device-level fencing epoch in addition to Session/Domain Lease generation and `edge_boot_id`.
- Observation authorization boundary without a fourth Presence Mode.
- Device-scoped audit and deterministic regression acceptance criteria.

### Out of scope

- Implementing a new authenticated transport, OEM integration, motion control, physical safety certification or production-grade identity proof in this document.
- Marketplace Booking or commercial allocation of a robot; a Booking cannot itself seize the device.
- Delegated TotalMersion, employee operators masquerading as the Identity Owner or a fourth Presence Mode.
- G-Brain, experience provenance, recorded sensory experiences or memory transfer.
- Defining the maximum number of simultaneous genuine live TotalMersion Sessions for one Identity Owner across *different* robots (C-2, separate RFC).

## 4. Trusted physical-resource identity and execution class

For the **reference physical v0.1** a trusted deployment MUST bind exactly one `edge_id` to one independently controlled physical robot, and all Runtime-protected physical commands to that robot MUST pass through that one Edge. This is a **provisioning assumption**, not a verified cryptographic hardware identity.

- Multiple `edge_id`s MUST NOT independently authorize commands for the same physical robot.
- `edge_boot_id` identifies a **boot**, not a robot and not a replacement for device-wide fencing.
- Edge execution class MUST come from **trusted provisioning**, not a client claim. A missing, unknown or unverified execution class MUST be treated as `physical` and subject to exclusivity.
- An explicitly trusted `digital` classification may bypass *physical-device* exclusivity only for an endpoint with no shared physical actuators. Reclassification MUST revoke/fence all dependent active authority and require re-registration.
- An Edge hosting multiple robots, distributed enforcement endpoints for one robot or a globally federated device registry requires a separate contract and review; it MUST NOT silently claim v0.1 compliance.
- The reference simulator lacks this execution-class field today; it is not currently a production-deployable physical integration.

## 5. Device slot lifecycle and authorization (P0-1)

### 5.1 Durable slot state

Core MUST store one device control-slot record in durable storage, serialized per physical device, with a **finite configured timeout** for a suspended holding Session. States are:

| State | Meaning |
| --- | --- |
| `free` | No effective prior authority remains; verified fencing/safe state permits a new acquire |
| `held(session_id, device_epoch)` | One Session owns the physical command slot |
| `transferring(from_session_id, to_session_id?, device_epoch, deadline)` | Old Session is being fenced; successor is not yet effective |
| `quarantined(device_epoch, reason)` | Safety/fencing confirmation is missing or contradictory; no new Session may become effective |

`quarantined` is an explicit fail-closed state. **A timeout by itself MUST NOT convert an unverifiably fenced device to `free`.** Recovery requires trusted Edge reconciliation and locally confirmed safe state (or an explicit, authenticated recovery procedure with equivalent evidence). The Core's availability objective cannot override this safety constraint.

### 5.2 Acquire, release and hold

1. Session creation, a client connection, passive observation, a Booking, or a valid Grant MUST NOT acquire the device slot.
2. The authorized controlling Session MUST explicitly `acquire` the slot in an audited, serialized Core transaction **before any effective device command Lease can be issued**.
3. While the slot is `held`, requests to acquire the same robot from other Sessions MUST fail `device_busy`, regardless of requested Control Domain.
4. An ordinary Session B **MUST NOT preempt** Session A. Session B MUST NOT initiate fencing of A through a standard acquire request. Only (a) a release authorized by the current holder or (b) separately authenticated, scoped administrative revocation may start fencing A. The privileges must not be inferred from a Booking, valid Grant or general client login.
5. The slot remains held when A is `active` or `suspended`; expiration of one Lease, loss of transport, or a transient liveness failure **does not automatically free the slot**.
6. Release can be requested by the authorized holder, triggered by Session end, loss of **all** supporting Grants, authenticated administrative revocation, or expiry of a configured finite `slot_hold_timeout` while `suspended`.
7. Release always enters a fenced/transfer-pending phase. It becomes `free` only after the Edge/OEM integration has confirmed that old authority is unusable and accepted actions have reached an agreed safe completion/stop condition.
8. `slot_hold_timeout` expiration starts release/fencing; it is **not** by itself permission for B to acquire. A finite transfer deadline MUST be configured; on unsafe or unverified failure, enter `quarantined`, not `free`.
9. Once released, suspended A cannot silently regain authority; it must perform a fresh authorized acquire, with a new, higher device epoch.
10. `end_session` and terminal `session.ended` behavior are not currently implemented in Core and must be added before relying on Session end as a release trigger.

### 5.3 Controller authorization and control scope

Core MUST authenticate and authorize the caller for the particular device and requested operation: `acquire`, `release`, or `admin_revoke`. Representation Grant, Session Policy and Compliance Policy are still required for every protected Lease. They do not, independently, grant device-administration or preemption rights.

## 6. One device-epoch authority and Edge recovery (P0-2)

1. **Single serialized issuer:** For each physical device, exactly one Core authority (single writer) MUST allocate device epochs and mutate the slot. Multiple Core processes using the same serialized durable store MAY implement this authority; independently writing Core instances MUST NOT claim conformance without shared serialization.
2. **Durable ordering:** `device_epoch` MUST be a strictly increasing integer persisted by Core atomically with each slot ownership/fencing transition. No caller, Session, Edge transport or Marketplace client can choose it.
3. **Lease binding:** Every physical Edge authority installation and accepted command MUST be bound to `(edge_id, edge_boot_id, device_epoch, session_id)` in addition to the existing Lease ID, Controller, domain generation and expiry.
4. **Boot-scoped Edge watermark:** During one authenticated boot, Edge MUST remember the highest device epoch and controlling Session associated with it. It MUST reject installs, revokes and commands from a **lower** epoch and reject an **equal** epoch associated with a *different* Session. It MUST reject a later install attempting to bypass a pending fence/safe-stop transition.
5. **New boot:** On reboot, Edge starts with **no installed authority** and obtains a fresh, non-reused `edge_boot_id`. Core MUST reject boot-ID reuse, discard all undelivered old-boot updates, invalidate old authority and reconcile the device slot before any command authority becomes effective. Given these preconditions, an Edge-local persistent high-water mark across boots is **not** required for reference v0.1. Core's device-epoch record remains durable across restarts.
6. **Core restart / recovery:** After a Core crash or restart, Core MUST NOT grant new device authority from unverified persisted `held`, `transferring` or `quarantined` state. It must obtain authenticated Edge state including current `edge_boot_id`, installed `device_epoch`, controlling `session_id` and fencing/safe-state readiness, or use a separately specified recovery process providing equivalent proof. Timeout alone does not establish safe completion.
7. **Unknown identity or conflict:** If identity binding, authority order, Edge state, acknowledgement authentication or device safety readiness is unavailable/contradictory, new physical authority MUST fail closed.

The Edge needs an authenticated Core-to-Edge control channel and authenticated acknowledgements for conformance; the reference Python class does **not** implement those network trust boundaries.

## 7. Control and TotalMersion invariants (P0-3)

1. Core and Edge MUST enforce **one controlling Session per physical device** regardless of which Control Domain is requested.
2. Within the selected Session, the RFC-0001 rule remains **one active Controller per Control Domain per Session**. Bridge may distribute different domains among different Controllers.
3. Core Lease issuance alone MUST NOT be reported as *effective physical device control*. Effectiveness requires Edge acknowledgement and device epoch/slot confirmation.
4. A Session's valid Grant does not imply controlling-Session authority or the right to displace another Session.
5. Device-level fencing MUST invalidate the **entire previous controlling Session** on that device, across all domains.
6. Edge MUST reject stale, delayed, reordered and replayed prior-session authority and commands across transfers, including after a new boot/reconciliation.
7. OEM-local safety and physical emergency stop MUST remain independent and higher priority than Runtime authorization.
8. No transition in this RFC changes the existing meaning of any Presence Mode.
9. **Owner-only TotalMersion v0.1:** A `totalmersion` Session MUST use only a high-level Controller for whom the trusted host establishes an authenticated, non-delegated binding to that Session's `owner_id`. Core MUST reject activation, mode change, Lease issuance and device-slot use when that binding cannot be verified, with `totalmersion_owner_mismatch`. `set_policies` MUST reject any proposed TotalMersion controller authorization without an authenticated Owner binding. This condition cannot be overridden by the Session Policy, Booking, Grant, employee role or any asserted `owner_presence_confirmed` boolean.
10. **Identity IDs are not interchangeable:** `controller_id` need not literally equal `owner_id`; the host must prove a trustworthy mapping between authenticated human Controller identity and the represented natural person. Technical heartbeat is not proof of identity or conscious human presence. The host-to-Core proof mechanism, verification lifecycle and Edge confidence boundary require an implementation contract before this condition can be claimed as enforced. Organizational Identity Owners require a separate approved live-delegation design before they can assert personal TotalMersion.
11. Employee/delegated operator TotalMersion and G-Brain-originated control are **not authorized by this RFC**. Any future support needs a separate Accepted RFC and truthful disclosure of who actually controls the representation.
12. These requirements **are not implemented today**. The reference Core currently trusts a supplied `owner_presence_confirmed` flag and a policy Controller ID; it does not establish the Owner binding in item 9.

**C-2 distinction:** This RFC addresses device exclusivity. It does **not** establish that one Identity Owner can genuinely be live in two concurrent TotalMersion Sessions on *different* robots. That separate human-presence exclusivity problem is C-2; do not advertise or infer true simultaneous live presence until C-2 is resolved.

## 8. Non-preemptive device handoff and safe-state ACK (P1-2)

Conceptual sequence only; no wire protocol is currently implemented:

1. Session B requests `acquire`. If A holds the device, B receives `device_busy`. B does **not** initiate a transfer.
2. The authorized holder A explicitly requests release, or an authenticated device administrator requests revocation independently of B's acquire.
3. Core validates credentials and current state, advances the durable device epoch and sets `transferring(from=A, to=null, ...)`, without issuing B effective control.
4. Edge receives authenticated device-wide fencing. All previous A Leases and command acceptance paths are disabled, regardless of domain.
5. The **local OEM integration**, not Runtime Controller A, B or an autonomous fallback identity, must report completion/stopping of already accepted actions into the configured safe state. Fencing new incoming commands alone does not prove ongoing actions have stopped.
6. Edge sends an authenticated fencing/safe-state ACK identifying the device, boot, epoch and former Session **only after both** old authority rejection and local safe-state confirmation. If such confirmation is unavailable, fail closed and quarantine.
7. Core records successful release into `free`, then B may issue a new authorized `acquire`. A new epoch is allocated and the new Session's Leases become effective only after authenticated Edge install acknowledgement.
8. Audit distinguishes *requested*, *fenced*, *released*, *issued* and *effective*. A delayed ACK for an earlier epoch cannot change current control state.

Any `Autonomous` fallback under RFC-0003 is **within the already-authorized Session** and does not transfer the device slot. Physical inter-Session release/transfer uses OEM-local safe completion, not a Runtime Controller masquerading as fallback.

There is no guaranteed zero-interruption physical handoff in v0.1; a conservative stop-before-start policy is intended.

## 9. Observation boundary without a fourth Presence Mode (P1-3)

**Decision proposed for v0.1:** Observation-only access is a **read-only participant/subscription within the current controlling Session**, not an independent `active` observation-only Session. This avoids conflicting with RFC-0003: every `active` Session continues to have exactly one of `autonomous`, `bridge` or `totalmersion`.

- Core/the trusted host MUST explicitly authorize observers through the applicable Grant, Session Policy and observation permissions; a client cannot self-assert an observer role.
- An observer receives **no Control Lease**, cannot issue commands, `acquire` a device slot, request transfer or be upgraded into a Controller via observation access.
- Observation subscriptions never occupy the physical device slot. When the controlling Session ends or loses the requisite authorization, the observation subscription MUST be revoked or re-authorized against a different controlling Session.
- Recording/telemetry permissions are distinct from command authority and must be enforced separately. This RFC does not define retention or legal consent for observed third parties.
- The read-only subscription API is **NOT IMPLEMENTED** in the reference Core. No observer-specific Presence Mode or Session status is introduced by this RFC.

**Deferred:** Independent observation-only Sessions are not part of v0.1 C-1; they would require a separate schema/lifecycle decision (and explicit treatment of null `presence_mode`) before adding them.

## 10. Device-scoped audit and effective state (P1-5)

Core MUST maintain a durable, **strictly ordered per-device** transition record. Each entry MUST identify at least:

- trusted device/Edge identity, `edge_boot_id` and `device_epoch`;
- prior and new `session_id` where applicable;
- operation/actor class, reason, correlation ID and device transition sequence;
- status: `acquired`, `release_requested`, `fence_requested`, `fenced_ack`, `released`, `effective`, `quarantined`, `denied` or equivalent explicit types.

Core MUST emit correlated per-Session events for affected Sessions. It MUST NOT publish an `effective` device-control event until the corresponding authenticated Edge acknowledgement for the **current** epoch and safe-state prerequisites have been validated.

The current reference Core emits `lease.issued` and `control.handover` before Edge ACK. Those currently describe **Core-side issuance within a Session**, not proven physical effectiveness. The later implementation MUST introduce separate device-scoped events rather than retroactively calling early issuance events physical handover.

## 11. Failure behavior and proposed regression tests

| Scenario | Expected behavior after implementation |
| --- | --- |
| Session B tries to seize a robot still held by A | `device_busy`; A remains authoritative |
| A is `suspended` and some Leases expire | Slot remains held until authorized release or configured suspended hold timeout |
| `slot_hold_timeout` expires | Begin fencing; only confirm `free` after Edge/OEM safe-state ACK; else quarantine |
| Two Sessions race to acquire same physical robot | At most one effective controlling Session |
| Sessions request different domains on same robot | Second controlling Session still denied |
| Prior Session install/command after new epoch | Edge rejects it as stale |
| Same epoch, another `session_id` | Edge rejects `device_epoch_conflict` |
| Core restart / Edge new boot | No stale authority revived; recovery reconciles device and boot |
| Physical Edge class absent/untrusted | Treat as physical, never silently exempt from exclusivity |
| Non-Owner Controller requests `totalmersion` Lease | Reject `totalmersion_owner_mismatch` despite Session Policy |
| Observation participant tries to command/acquire | Deny; no Control Lease or slot transition |
| One Session in `bridge`, multiple domain Controllers | Valid with independent scoped Leases |
| Two distinct robots, different controlling Sessions | Permitted, subject to separate Owner live-presence C-2 constraints |
| Parallel purely digital Sessions | Permitted without physical device slot |
| Core issues a Lease before Edge ACK | No physical `effective` event yet |
| OEM reports in-flight action not safely completed | No successor effective; quarantine or remain pending |

Proposed stable denial codes include: `device_busy`, `device_transfer_pending`, `device_epoch_stale`, `device_epoch_conflict`, `device_state_unverified`, `totalmersion_owner_mismatch` and `observation_only_access`. They are **not** yet implemented API errors.

Tests MUST distinguish simulated reference guarantees from actual robot safety. CI success cannot certify physical hardware.

## 12. Alternatives, trade-offs and remaining review decisions

**Option A (recommended): one controlling Session per physical robot.** Simpler safety/authorization boundary, but a single robot cannot independently serve two controlling Sessions at once. AI and Owner may still share domains *within one Session* using Bridge.

**Option B (deferred): one controlling Session per (physical device, domain).** Would require device-wide cross-domain safety coupling, coordinated handoff and separate acceptance; the present (Session, Domain) key does **not** provide B.

**No change (not recommended):** permits competing device commands under separately valid Sessions.

Before marking this Draft **Accepted**, a maintainer must explicitly confirm:
1. Trusted v0.1 one-Edge-per-device binding and the fail-closed physical-default execution class.
2. The `free / held / transferring / quarantined` slot model, authorized non-preemptive release, and timeout/recovery safety.
3. The single durable Core epoch issuer and its relationship to `edge_boot_id`; authenticated Edge state/ACK requirements.
4. Owner-only `totalmersion` authentication contract, including the Controller→Owner binding and organizational Owner handling.
5. Observer-as-participant model versus independent observation Sessions.
6. The minimum testable simulated safe-state/ACK boundary, with no claim of OEM certification.
7. A separate C-2 RFC for Owner live-presence concurrency across robots.

## 13. Delivery plan following acceptance

1. Align RFC-0001, RFC-0003, RUNTIME_REQUIREMENTS.md, README.md and ARCHITECTURE.md so that Session/domain authority and physical-device authority are described consistently.
2. Define physical/digital execution class, authenticated Owner-binding evidence, slot+device-epoch storage, protected Edge messages and read-only observer authorization.
3. Implement `end_session` / `session.ended` (a dependency for terminal slot release), durable slot management, authenticated ACK/recovery and device-scoped audit.
4. Implement Core + Edge device-level checks and deterministic race/replay/stop/boot regression tests in a **separate implementation PR**.
5. Keep Marketplace, G-Brain, C-2 and actual OEM adapter work out of C-1. An OSS reference passing software tests does not establish production-ready robot control.

**Deferred horizon:** employee operators, truthful controller/experience provenance and G-Brain must not silently redefine the three current Presence Modes.
