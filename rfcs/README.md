# Twin Runtime RFC process

RFCs are proposals for significant or normative changes to Twin Runtime. The maintainer decides whether a proposal is accepted. An RFC being merged into the repository is not, on its own, proof of implementation or certification.

## When an RFC is required

Start with a public **Issue** describing the problem and scope. Before implementation, submit an RFC PR when proposing changes to any of:
- public protocol or API contracts;
- representation, identity/authorization or trust semantics;
- Session, Presence Mode or Control Lease behavior;
- safety, fallback or Edge enforcement;
- adapter interfaces or normative schemas under `spec/`.

Routine bug fixes, documentation, tests and examples do not need an RFC unless they change these contracts. Use the [contribution path](../CONTRIBUTING.md#where-to-start).

## How to submit

1. Open an Issue to agree on problem and scope, and link it from the RFC.
2. Add a file `RFC-NNNN-short-title.md` under `rfcs/`, using the next unused number. Open a PR limited to the RFC and supporting non-normative discussion.
3. Use one of these statuses in the RFC header:
   - **Draft:** work in progress;
   - **Proposed:** ready for maintainer review and decision;
   - **Accepted:** explicitly approved by the maintainer;
   - **Rejected:** not accepted;
   - **Superseded:** replaced by a later accepted RFC.
4. The maintainer records the outcome in the PR and updates the RFC status. **Do not implement a significant change before the relevant RFC is accepted.**

Existing RFC-0001 and RFC-0002 are Draft; RFC-0003 is Proposed pending acceptance. No status change here asserts that any unimplemented requirement already exists in Runtime Core.

Security vulnerabilities must be [reported privately](../SECURITY.md), not proposed via public Issue or RFC.
