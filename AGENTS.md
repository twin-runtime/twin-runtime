# Twin Runtime - Agent Instructions

## Project purpose

Twin Runtime is an open-source runtime for connecting humans, AI systems and humanoid robots.

The project is intended to enable third-party developers and companies to build commercial adapters, integrations and applications on top of Twin Runtime.

## Core architectural rules

1. Twin Runtime is NOT a replacement for ROS 2 or manufacturer SDKs.
2. Integrate with existing robotics stacks instead of rebuilding them.
3. Keep the runtime independent from the Twin.rent Marketplace.
4. Do not introduce mandatory dependencies on proprietary Twin.rent services.
5. Do not introduce mandatory control-plane frameworks unless explicitly approved in an architectural decision or RFC.

## Control model

Twin Runtime must support three presence modes:

- Autonomous
- Bridge
- TotalMersion

TotalMersion means the Identity Owner is live and in control for the entire session.

Control devices such as keyboard, gamepad, VR, motion capture or future BCI are separate from presence modes.

## APIs

Maintain separation between:

- Intent API - high-level commands and actions
- Realtime API - continuous control streams

Never expose raw motor or torque control through a public internet API.

## Safety

Safety takes priority over functionality. Do not bypass manufacturer safety systems.

Robot adapters must follow the [adapter contribution and safety checklist](CONTRIBUTING.md#robot-adapters-and-integrations), including the applicable mandatory heartbeat, stop, loss-of-connection and lease-expiration requirements.

## Contributions

Prefer small, reviewable changes. Follow the single [Issue / PR / RFC / Security contribution path](CONTRIBUTING.md#where-to-start).

Significant new normative protocol, API, authorization, safety, Session, control or adapter-interface changes require an Issue followed by an Accepted RFC, using [rfcs/README.md](rfcs/README.md). The v0.1 experimental reference implementation predates this process; clearly labeled prototypes against Proposed RFCs are permitted without claiming normative acceptance.

## Testing

New functionality must include appropriate tests.

Do not claim adapter compatibility or certification while no published Twin Runtime conformance suite or verification process exists. See [CONTRIBUTING.md](CONTRIBUTING.md#robot-adapters-and-integrations).

## Licensing

Twin Runtime code is licensed under Apache License 2.0.

Do not add dependencies or code with incompatible licensing without explicit approval.

## Security

Never commit:
- secrets,
- API keys,
- credentials,
- private customer data,
- private Twin.rent Marketplace data.

Follow SECURITY.md for vulnerability reporting.
