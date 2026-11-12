# Identity and Representation Grant Contract

**Scope:** Twin Runtime v0.1 reference contract clarification  
**Status:** Documentation alignment, not a new schema or API  
**Last reviewed:** 2026-11-12

This document clarifies the identity and authorization field mapping used by the existing v0.1 JSON Schemas and Python reference Core. It introduces **no** Runtime features, Marketplace dependencies or new legal rights.

## 1. Identifiers and roles

| Field / entity | Meaning in v0.1 | Must not be mistaken for |
| --- | --- | --- |
| `RepresentationGrant.owner_id` / `Session.owner_id` | Stable opaque identifier for the **human or organization whose identity or presence is represented** (Identity Owner) | Licensor, legal rights holder, signatory, payer, AI agent, operator |
| `RepresentationGrant.authorized_subject` | Stable opaque identifier of the **logical technical representation subject** whose representation is authorized | Controller, robot, Edge, Listing, Booking, legal contract |
| `Session.representation_subject_id` | Representation subject selected for this Session; must equal the supporting Grant's `authorized_subject` | `owner_id`, `controller_id`, `edge_id` |
| `RepresentationGrant.provider_id` | Opaque identifier of the Representation Provider / claimed issuer provenance | Authenticated proof of issuer trust |
| `SessionPolicy.controller_authorizations[].controller_id` | Controller allowed by that Session Policy to use specified Presence Modes and Control Domains | Identity Owner by default, authorized subject, rights holder |
| `ControlLease.controller_id` | Actual controller of record for one Session + Control Domain, subject to policy and Lease checks | A free-standing representation right |
| `Session.edge_id` | Enforcement endpoint associated with the Session | Logical representation subject |
| `Deployment.twin_instance_id` | Optional instance / embodiment reference in the conceptual Deployment model | The Grant's representation subject |
| `authorization_reference` / `authorization_version` | Optional opaque reference and version for an external underlying authorization artifact | A verified license, a signature or a Core-enforced version check |

At Lease issuance, reference Core compares `grant.owner_id == session.owner_id` and `grant.authorized_subject == session.representation_subject_id`. It checks Grant status, time window, permitted Presence Mode and Control Domain. Session Policy separately authorizes the selected Controller. There is no implicit mapping from `authorized_subject` to `controller_id`.

**Representation is not embodiment.** One logical representation subject can be used with different capable physical or digital implementations. The specific robot/device/Edge is a different concern.

## 2. Person, organization and rights holder

Identity Owner may be a real person **or an organization**. An organization can be represented as an organization. An organization holding a license to portray a separate person does **not** become that portrayed person for Runtime purposes. The represented owner, licensing party, signatory and customer may be different entities. Runtime Core does not model or verify their legal relationship.

For a representation of a historical person, the rights holder may authorize a technical representation, but a human operator or AI Controller cannot truthfully be presented as the historical person personally joining live. TotalMersion denotes live presence of the actual Identity Owner, not merely a human controlling someone else's likeness.

An organizational Identity Owner also raises a question about authorized human delegates in live-human modes. The present reference Core does not implement organizational delegation, verification of signatory authority, or proof that a claimed delegate is genuinely acting for an organization. **Do not assert production-grade Bridge/TotalMersion identity guarantees from the simulator's liveness flag.** Organizational live-presence semantics need a separate decision before production use.

## 3. Namespaces and uniqueness

Identifiers are opaque strings. The reference Core uses direct string equality and does not derive authority from prefixes. Providers integrating into one deployment should issue collision-resistant IDs, with a provider-qualified namespace where appropriate, for example:

```text
provider_id:    provider-example
owner_id:       provider-example:owner:7f4c...
authorized_subject: provider-example:representation:d213...
grant_id:       provider-example:grant:5e92...
```

These are **examples, not mandated wire formats**. Distinct providers must not accidentally use identical owner, subject or Grant identifiers for unrelated entities. Conversely, separately scoped identifiers must not be silently treated as proof that two providers refer to the same real-world identity. Cross-provider identity resolution and federated provider trust are deferred.

**Critical:** a namespace-qualified `owner_id` does not authenticate the issuer. `provider_id` is currently a recorded string, not a cryptographic assertion or an entry checked against a trusted issuer registry.

## 4. Technical authorization boundary

1. The reference Core provisions Grants only through trusted local administrative input. JSON Schema validity does not prove that a provider is authorized to represent the owner.
2. Grant constrains representation scope (`allowed_presence_modes`, `allowed_control_domains`, validity, status); it **does not** currently restrict `controller_id` or controller class.
3. Session Policy selects specific Controllers for each mode and domain; a Control Lease authorizes temporary scoped control. The Edge enforces installed Lease authority and rejects stale or expired commands.
4. The reference simulation uses host-supplied Controller identity and `owner_presence_confirmed`; it does **not** independently authenticate a real human, verify consent or establish actual human attention.
5. The v0.1 `restrictions` object is deliberately closed and empty. Geography, licensed purpose, permitted data use and other legal/commercial constraints cannot currently be enforced through that field.
6. The underlying legal agreement and the relationship of rights holder to owner remain outside Runtime Core.

Future issuer-imposed Controller restrictions, third-party issuer verification, signatures, organization-delegate verification and substantive restrictions each require a separate security design and specification change. They must not be described as implemented.

## 5. Expiration and revocation

Reference Core exposes `revoke_grant(grant_id)`: it marks that whole Grant revoked, invalidates dependent Leases and enqueues Edge authority revocation. An Edge that has not yet received a revocation can retain installed authority **only until its bounded local TTL**, currently at most 60 seconds. This is not a guarantee of instant revocation across disconnected systems.

There is no automatic Marketplace-to-Core revocation channel. A withdrawn external license does not affect Core until trusted provisioning invokes a corresponding revocation or the Grant's own validity ends. A valid Grant may be reused by multiple Sessions, and the current v0.1 Core does not support partial Grant amendment.

`authorization_reference` and `authorization_version` are optional traceability metadata, not authoritative Core checks. A provider may keep a versioned external authorization ledger, but no booking or license entity is required by Runtime.

## 6. Future compatibility (no implementation in this PR)

- External providers can map their own rights and session/transaction context into Runtime Grants. Runtime remains independent of proprietary Marketplace IDs.
- Technical representation subject, identity owner, current Controller and physical device remain distinct concepts.
- Future controller restrictions in Grants require a separate RFC; Session Policy still governs per-Session Controller assignment.
- Any addition of Presence Modes, organizational delegation or synthetic personas requires explicit semantic and safety review. No fourth Presence Mode is added here.

## 7. Sources of truth in this repository

- `spec/v0.1/representation-grant.schema.json` and `spec/v0.1/session.schema.json` - current validated wire fields.
- `reference/runtime_core.py` - current implementation of field equality, policy checks and Grant revocation.
- `rfcs/RFC-0003-command-lease-grant-session.md` - separation of representation authority and Controller authority.
- `rfcs/RFC-0002-identifiers-events-data-model.md` - opaque identity references and deployment concepts.
- `RUNTIME_REQUIREMENTS.md` - normative requirements; not every requirement is implemented by the reference prototype.
