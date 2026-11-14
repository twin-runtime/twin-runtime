# Contributing to Twin Runtime

Twin Runtime is an Apache-2.0 open-source project. Independent developers, researchers, integrators and robotics manufacturers can use it commercially, fork it and propose improvements. **Anyone can open a Pull Request (PR) from a fork without collaborator access.** Maintainers decide what is merged.

## Where to start

| Change | First step |
| --- | --- |
| Small documentation, test, example or demo fix | Open a focused PR directly |
| Reproducible non-security bug | Open a Bug Issue; then a PR if you have a fix |
| New feature for this repository or an integration requiring changes here | Open a Proposal or Integration/Adapter Issue before implementation |
| Independent external adapter using existing Runtime interfaces | No Issue, PR or maintainer approval required under Apache-2.0 |
| New normative change to protocol, public APIs, authorization, safety model, Session or Control semantics, adapter interface or schemas | Open an Issue, then submit an RFC as a PR under `rfcs/`; normative implementation follows an Accepted RFC |
| Security vulnerability or bypass | **Report privately**, following [SECURITY.md](SECURITY.md). Never open a public Issue or PR disclosing the vulnerability |

The [RFC process](rfcs/README.md) defines proposal statuses, an explicit v0.1 experimental-prototyping transition and acceptance. GitHub Discussions are not enabled; use an Issue (a blank Issue is allowed) for technical questions or proposals. For substantial changes, an Issue is the default starting point, not an unreviewed implementation PR.

## Pull Request workflow

1. Read the [local quick start](README.md#try-the-live-demo-locally) and relevant architecture/RFC documents.
2. Fork the repository, create a branch and make a small, reviewable change. Add tests for changed behavior.
3. Add a DCO sign-off to **every new commit in your PR**, including maintainer-authored commits, as described below.
4. Open a PR and describe the problem, what changed, any authorization/security impact, related Issue or RFC, and test results.
5. Wait for maintainer review and automated checks before merge. An open PR does not imply acceptance.

Avoid dependencies or copied code that conflict with Apache-2.0 or for which you lack permission. Keep Runtime Core independent of any Twin.rent Marketplace, identity provider, AI vendor, transport or robot manufacturer.

## Robot adapters and integrations

**For now, OEM/robot adapters belong in separate repositories** maintained by their producers or integrators. The reference repository does not yet provide a stable adapter interface, published conformance suite or physical-hardware safety validation. **Independent external adapters need no Issue, approval or license from the maintainers beyond Apache-2.0.** Open an Integration/Adapter Issue if the adapter needs changes to this repository; normative Core/adapter-contract changes require an Accepted RFC first.

Robot adapters **must support, where applicable, capability reporting, heartbeat, stop, connection-loss handling and Control Lease expiry**, without bypassing OEM safety systems. Describe the external adapter's Intent API or Realtime API integration, Control Domains and responsible operator, and provide a self-assessment covering:
- capability reporting and controller/Control Domain boundaries;
- heartbeat and communication-loss handling;
- stop and fail-safe behavior;
- Control Lease expiry and revocation;
- preservation of OEM safety mechanisms.

For each applicable mandatory mechanism, describe how it is supported; for non-applicable items, explain why. A self-assessment does not replace implementing applicable safety safeguards.

Never bypass manufacturer safety controls or expose raw motor/torque control through a public internet API. Document who is responsible for integration, deployment and hardware safety; a self-assessment is **not** an independent safety review.

Do not label an adapter **"Twin Runtime compatible"** or **"certified"** until published conformance tests and a defined verification process exist and have been satisfied. Conformance, when available, will not be physical robot safety certification.

## Developer Certificate of Origin (DCO)

Contributors certify they have the right to submit each contribution under Apache-2.0. Read the [Developer Certificate of Origin](https://developercertificate.org/).

Sign off **all newly authored non-merge PR commits, including maintainer commits, from this policy onward**. DCO checks skip merge commits created while updating a PR branch, not independently authored changes. Do not rewrite already-merged history just to add signatures.

```bash
git commit -s -m "fix: describe the change"
```

This adds a trailer such as `Signed-off-by: Your Name <you@example.com>`. When committing through an API or web editor, include the same trailer in the commit message. The PR DCO workflow checks for the trailer in each non-merge PR commit; it does not independently verify copyright ownership or employer consent.

If your latest local commit is missing the trailer, use `git commit --amend --signoff --no-edit` and update the PR branch. For multiple unsigned PR commits, use `git rebase --signoff` with care, then update your PR branch. Never rewrite the protected `main` history.

## Commercial use

Twin Runtime is Apache-2.0. Paid integrations, adapters, services and products are allowed under the license without a Twin.rent account, booking or revenue share. Commercial Marketplace functions such as listings, bookings and payments are outside Runtime Core.

## Security

Report suspected vulnerabilities privately following [SECURITY.md](SECURITY.md); do not publish exploit details in GitHub Issues or PRs.
