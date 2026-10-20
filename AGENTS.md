# Twin Runtime - Agent Instructions

## Project purpose

Twin Runtime is an open-source runtime for connecting humans, AI systems and humanoid robots.

The project is intended to enable third-party developers and companies to build commercial adapters, integrations and applications on top of Twin Runtime.

## Core architectural rules

1. Twin Runtime is NOT a replacement for ROS 2 or manufacturer SDKs.
2. Integrate with existing robotics stacks instead of rebuilding them.
3. Keep the runtime independent from the Twin.rent Marketplace.
4. Do not introduce mandatory dependencies on proprietary Twin.rent services.
5. Do not introduce Open Mercato or any other control-plane framework unless explicitly approved in an architectural decision or RFC.

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

Safety takes priority over functionality.

Every robot adapter must support, where applicable:

- capabilities reporting
- heartbeat
- stop
- connection-loss handling
- control-lease expiry

Do not bypass manufacturer safety systems.

## Contributions

Prefer small, reviewable changes.

Significant changes to:
- protocol,
- APIs,
- safety model,
- session model,
- control model,
- adapter interfaces

must first be proposed through an Issue, Discussion or RFC.

## Testing

New functionality must include appropriate tests.

Robot adapters must eventually pass Twin Runtime conformance tests before being described as compatible.

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
