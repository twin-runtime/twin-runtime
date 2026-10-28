# Twin Runtime Architecture

**Status:** Architecture Baseline v0.1  
**Project:** Twin Runtime  
**License:** Apache-2.0

---

## 1. Purpose

Twin Runtime is an open-source runtime for managing human presence across AI systems, digital representations and physical robots.

Its purpose is to provide a common layer for:

- representation of a specific person or organization,
- presence modes,
- temporary and scoped control authority,
- control handover,
- runtime enforcement,
- fallback behaviour,
- audit and events,
- integration with external AI, transport and robotics systems.

Twin Runtime is not a replacement for existing robotics, AI or realtime communication technologies.

It is an interoperability and presence layer above them.

---

## 2. Core Architectural Principle

Twin Runtime integrates existing technologies rather than rebuilding them.

Twin Runtime does not replace:

- ROS 2,
- LeRobot,
- OEM robot SDKs,
- WebRTC or other realtime transports,
- SLAM and navigation systems,
- motion controllers,
- stabilization and balance controllers,
- collision avoidance,
- emergency stop systems,
- AI models,
- personality engines,
- skill or policy frameworks,
- sensor-specific data pipelines.

These systems remain responsible for their own domains.

---

## 3. High-Level Architecture

```text
                 Identity Owner
                       │
                       ▼
            Representation Provider
       Twin.rent Marketplace / other issuer
                       │
                       ▼
              Representation Grant
                       │
                       ▼
              ┌──────────────────────┐
Compliance →  │     TWIN RUNTIME     │
Provider      │                      │
              │ Deployment Context   │
              │ Session              │
              │ Presence Mode        │
              │ Control Leases       │
              │ Fallback Policies    │
              │ Readiness            │
              │ Audit & Events       │
              └──────────────────────┘
                    │          ▲
           control  │          │ observations
                    ▼          │
             Transport Layer
           LiveKit / other
                    │
                    ▼
          Edge Enforcement Agent
                    │
                    ▼
        Robot Integration Layer
       LeRobot / ROS 2 / OEM SDK
                    │
                    ▼
         Humanoid / Digital Twin
                    │
                    └── sensors / telemetry
```

No specific transport, robotics framework, AI provider or marketplace is a mandatory dependency of Twin Runtime Core.

---

## 4. Identity Owner

The Identity Owner is the human or organization whose identity or presence is represented by a Twin.

The Identity Owner is separate from:

- the current operator,
- an AI agent,
- the humanoid,
- the control device,
- the Representation Provider,
- the customer booking the Twin.

This distinction is fundamental to Twin Runtime.

---

## 5. Representation Provider

A Representation Provider supplies the technical authorization that a specific person, AI system or service may represent an Identity Owner under defined conditions.

Twin.rent Marketplace may act as a Representation Provider.

Other providers must also be possible.

Twin Runtime must therefore be usable without a Twin.rent account or proprietary Twin.rent service.

---

## 6. Representation Grant

A Representation Grant describes technical authorization to represent an Identity Owner.

It can express:

- who is represented,
- who or what may represent them,
- permitted context,
- permitted Presence Modes,
- validity period,
- restrictions,
- revocation status.

A Representation Grant does not automatically grant control of a robot.

A valid Control Lease must be issued separately.

A Representation Grant is a technical authorization artifact and is not, by itself, a replacement for the underlying legal agreement, consent or commercial license.

---

## 7. Deployment and Session

Twin Runtime distinguishes between a **Deployment** and a **Session**.

### Deployment

A Deployment represents the broader physical or digital availability of a Twin in a place and time.

Example:

```text
18:00 arrival
18:10 readiness check
18:15 active
19:20 charging
19:50 active
21:00 deployment ends
```

A humanoid may be:

- transported to a location,
- waiting,
- charging,
- participating in multiple sessions,
- temporarily unavailable,
- transported away.

Transportation, logistics and booking are not Runtime Core responsibilities.

Runtime must, however, allow those states to be represented.

### Session

A Session is an active instance of presence and interaction within a Deployment.

A Deployment may contain multiple Sessions.

---

## 8. Operational State

Operational State is separate from Presence Mode.

Example Operational States include:

- transport,
- standby,
- ready,
- active,
- charging,
- degraded,
- unavailable,
- maintenance.

The final state model will be defined in Runtime Requirements.

---

## 9. Presence Modes

Presence Mode describes how the Identity Owner, AI and other control sources participate in a Session.

Presence Mode is independent of:

- control device,
- transport technology,
- robot manufacturer,
- AI provider,
- robotics framework.

Twin Runtime defines three primary Presence Modes.

### 9.1 Autonomous

AI or another autonomous controller operates the relevant control domains.

If the Twin represents an Identity Owner, autonomous behaviour must remain within the applicable Representation Grant and session policy.

---

### 9.2 Bridge

The Twin may operate autonomously while the Identity Owner can observe and take over selected control domains in real time.

Example:

```text
Before takeover:

conversation → AI
gesture      → AI
mobility     → AI
navigation   → AI

After Owner takeover:

conversation → Identity Owner
gesture      → Identity Owner
gaze         → Identity Owner
mobility     → AI
navigation   → AI
```

Bridge does not require human and AI commands to be mathematically blended inside the same control domain.

An external controller may implement such behaviour, but it is not required by Twin Runtime Core.

---

### 9.3 TotalMersion

**Identity Owner is live for the entire TotalMersion period: real conversation, real presence.**

The Identity Owner holds the relevant high-level Control Leases.

Local safety and assistance systems may still perform:

- balance,
- stabilization,
- collision constraints,
- actuator protection,
- emergency stop,
- other local safety functions.

These functions do not constitute autonomous representation.

### Temporary interruption

TotalMersion does not require the entire Deployment to remain permanently in TotalMersion.

The Session may explicitly transition:

```text
TotalMersion
      ↓
Autonomous
      ↓
TotalMersion
```

or:

```text
TotalMersion
      ↓
Standby
      ↓
TotalMersion
```

If the Owner needs a break, loses connectivity or deliberately delegates control, the Presence Mode must change explicitly.

Twin Runtime must not continue presenting the Session as TotalMersion if the Identity Owner is no longer live.

Autonomous fallback is permitted only when authorized by the Representation Grant and Session policy.

---

## 10. Scoped Control Leases

Twin Runtime uses scoped Control Leases.

A Control Lease grants temporary authority over a specific control domain within a specific Session.

Core rule:

> **One active controller per control domain.**

Non-normative examples of control domains:

- `conversation`
- `voice`
- `gaze`
- `facial_expression`
- `gesture`
- `manipulation`
- `mobility`
- `navigation`

The final taxonomy is defined in Runtime Requirements and must remain extensible.

A Control Lease must conceptually support:

- issue,
- renew,
- revoke,
- expire,
- heartbeat / liveness,
- explicit controller identity,
- Session scope,
- control-domain scope.

An expired or revoked Lease must no longer authorize new commands.

---

## 11. Command Authorization Model

Possession of a Control Lease is necessary but not sufficient to execute an action.

Conceptually, an action can proceed only if:

```text
Capability exists
       AND
Representation Grant permits it
       AND
Presence Mode permits it
       AND
Compliance Policy permits it
       AND
Control Lease is valid
       AND
Edge Enforcement accepts it
       AND
Local OEM Safety permits execution
```

Local safety always has final authority.

---

## 12. Fallback Policy

Every controllable domain may define behaviour for loss of control, authorization or connectivity.

Examples:

```text
conversation lost → mute / AI takeover / standby
gesture lost      → neutral behaviour
mobility lost     → hold / safe stop
navigation lost   → stop / local navigation fallback
Owner disconnect  → standby / authorized Autonomous fallback
```

Fallback Policy specifies the desired reaction.

The physical implementation of the reaction remains the responsibility of the underlying integration and OEM stack.

A fallback must never silently change the semantic Presence Mode.

If TotalMersion falls back to autonomous representation, the Session must transition to Autonomous.

---

## 13. Edge Enforcement Agent

Twin Runtime includes an Edge Enforcement Agent positioned as close as practical to the controlled system.

Its responsibilities include:

- checking authorization before accepting control actions,
- verifying active Control Leases,
- rejecting unauthorized or stale commands,
- monitoring lease heartbeat,
- triggering configured fallback or safe-stop hooks,
- emitting enforcement and audit events.

The Edge Enforcement Agent does not implement robot motion control or physical safety.

It may request:

```text
safe_stop()
```

but the actual implementation is supplied by the robot integration or OEM stack.

Twin Runtime cannot guarantee enforcement if an integration bypasses the Edge Enforcement Agent or fails to implement required hooks.

---

## 14. Safety Boundary

Local safety has authority above Twin Runtime.

Conceptually:

```text
OEM Safety / Emergency Stop
            ↑
Local Motion & Stability
            ↑
Edge Enforcement
            ↑
Control Lease
            ↑
Human / AI Controller
```

Twin Runtime must never require bypassing local robot safety mechanisms.

Passing Twin Runtime conformance tests is not physical safety certification.

---

## 15. Observation and Telemetry Plane

Twin Runtime is bidirectional.

A Twin does not only receive commands. It also returns observations, state and sensory information.

Possible modalities include:

- vision,
- audio,
- depth,
- proximity,
- IMU,
- orientation,
- acceleration and g-force,
- temperature,
- thermal sensing,
- tactile sensing,
- pressure,
- force,
- torque,
- finger and hand tactile arrays,
- olfactory sensing,
- battery state,
- charging state,
- power consumption,
- joint and actuator telemetry.

The architecture must remain open to future sensor modalities.

Twin Runtime Core should not become a universal raw-data streaming system.

The architecture therefore distinguishes:

### Data Plane

High-volume realtime data such as:

- video,
- audio,
- depth,
- tactile streams,
- raw telemetry.

This may use LiveKit, ROS 2, OEM transports or other systems.

### Runtime Control and Event Plane

Twin Runtime manages:

- existence and availability of observation sources,
- authorization to access them,
- session association,
- metadata,
- state changes,
- events,
- references to external streams.

---

## 16. Energy and Readiness

Twin Runtime does not implement battery management.

It must, however, be capable of consuming operational information such as:

- battery level,
- charging state,
- estimated remaining runtime,
- thermal state,
- energy warnings,
- component availability.

Runtime may expose an aggregated **Readiness** state.

Example:

```text
Ready for planned deployment: NO
Reason: estimated battery runtime 74 minutes
Required deployment duration: 180 minutes
```

or:

```text
mobility: unavailable
conversation: available
vision: available
```

The underlying information comes from robot and infrastructure integrations.

---

## 17. Local Compliance

Physical and digital Twins may operate under different legal and regulatory requirements depending on jurisdiction, location and context.

Twin Runtime must support external compliance constraints without attempting to become a legal interpretation engine.

A **Compliance Policy Provider** may supply effective technical restrictions for a Deployment or Session.

Examples of policy dimensions include:

- whether recording is permitted,
- whether realtime transmission is permitted,
- whether autonomous operation is permitted,
- required human or AI indicators,
- sensor restrictions,
- geofencing,
- mobility restrictions,
- retention requirements,
- disclosure requirements.

Twin Runtime enforces the supplied technical policy where technically possible.

The Compliance Policy Provider remains responsible for determining the applicable policy.

---

## 18. Presence Disclosure

Runtime must expose the current Presence Mode and relevant control state so an integration can communicate whether a Twin is currently:

- autonomous,
- controlled by the Identity Owner,
- operating in Bridge mode,
- unavailable or in fallback.

The physical or digital method of disclosure is implementation-specific.

Examples may include:

- visual indicators,
- UI status,
- audio disclosure,
- external display,
- machine-readable metadata.

---

## 19. Audit and Events

Twin Runtime provides a common event model for presence, authorization and control decisions.

Examples include:

- Deployment created,
- Session created,
- participant joined,
- Representation Grant accepted,
- Representation Grant revoked,
- Presence Mode changed,
- Control Lease issued,
- Control Lease renewed,
- Control Lease revoked,
- Control Lease expired,
- control domain transferred,
- command accepted,
- command rejected,
- fallback activated,
- safe-stop requested,
- Readiness changed,
- Compliance Policy changed.

Audit must distinguish between:

- command requested,
- command authorized,
- command accepted by an integration,
- execution confirmed by an integration,
- actual physical execution.

Twin Runtime must not claim physical execution unless the underlying integration provides such confirmation.

Tamper-evident audit storage is not required in v0.1 architecture and may be added later.

---

## 20. MultiPresence

Twin Runtime must allow the data model to support multiple simultaneous Sessions associated with the same Identity Owner.

Example:

```text
Identity Owner
 ├── Tokyo Session
 ├── London Session
 ├── New York Session
 └── Warsaw Session
```

Each Session maintains independent:

- Representation Grants,
- Presence Mode,
- Control Leases,
- participants,
- Operational State,
- audit and events.

v0.1 does not require orchestration of multiple simultaneous Sessions.

The architecture must simply not assume:

```text
one Identity Owner = one Twin = one Session
```

---

## 21. Personality Provider

Personality is strategically important for representing a specific human.

Twin Runtime must allow an external Personality Provider to supply elements such as:

- communication style,
- behavioural profile,
- approved knowledge,
- memory,
- preferences,
- representation boundaries,
- voice or persona references.

Twin Runtime v0.1 does not define a proprietary personality format or Personality Engine.

---

## 22. Skill and Policy Providers

Skills and autonomous policies may come from external ecosystems.

Examples may include:

- Hugging Face / LeRobot policies,
- OEM capabilities,
- third-party AI systems,
- robotics frameworks,
- future skill repositories.

Twin Runtime does not define a proprietary universal skill format in v0.1.

It should allow future integrations to declare compatibility and required capabilities.

---

## 23. Experience Provider

Future systems may consume events and observations from one or multiple Twin Sessions and create information for the Identity Owner.

Possible outputs include:

- summaries,
- memories,
- commitments,
- opportunities,
- important interactions,
- requests for decisions.

This is the architectural basis for future MultiPresence experience aggregation.

A global Experience or G-Brain system is outside Twin Runtime v0.1.

---

## 24. Integration Independence

Twin Runtime Core must not require:

- Twin.rent Marketplace,
- LiveKit,
- LeRobot,
- ROS 2,
- a specific humanoid manufacturer,
- a specific LLM,
- a specific Personality Provider,
- a specific skill repository.

These technologies may have reference integrations.

They do not define Twin Runtime semantics.

---

## 25. Open Source Boundary

The intended Apache-2.0 scope includes:

- Runtime specification,
- Runtime Core,
- Control Lease model,
- Representation Grant technical model,
- Presence Mode logic,
- Edge Enforcement Agent,
- fallback model,
- audit/event schemas,
- integration interfaces,
- SDK,
- reference integrations,
- adapter templates,
- conformance tests,
- examples.

Twin.rent Marketplace remains a separate proprietary product.

Marketplace responsibilities include:

- commercial Identity Owner verification,
- KYC,
- contracts and commercial licensing,
- listings,
- bookings,
- payments,
- revenue sharing,
- customer data,
- marketplace analytics,
- commercial dispute handling.

---

## 26. Conformance

Twin Runtime compatibility must be testable.

Conformance tests should eventually verify at least:

- unauthorized commands are rejected,
- expired leases cannot continue controlling a domain,
- stale commands from a previous controller are rejected,
- handover correctly changes control authority,
- Presence Mode transitions are explicit,
- TotalMersion cannot silently continue after Owner presence is lost,
- fallback behaviour is declared,
- unsupported functionality is explicitly reported,
- audit events correctly represent Runtime decisions,
- integrations respect declared Compliance Policies,
- transports and robotics stacks can be exchanged without changing Twin Runtime semantics.

Conformance is software interoperability testing.

It is not robot safety certification or regulatory certification.

---

## 27. Non-Goals

Twin Runtime v0.1 does not aim to create:

- a replacement for ROS 2,
- a replacement for LeRobot,
- a new realtime transport,
- a robot motion controller,
- an emergency-stop system,
- a universal humanoid skill format,
- a new AI model format,
- a Personality Engine,
- a Skill Marketplace,
- a Robot Cloud,
- a battery management system,
- a legal compliance engine,
- a global Experience or G-Brain platform.

These systems may integrate with Twin Runtime.

---

## 28. Architectural Direction

Twin Runtime v0.1 follows this architectural direction:

> **Twin Runtime Core + Edge Enforcement Agent + scoped Control Leases + extensible integration interfaces, independent of Twin.rent Marketplace, LiveKit, LeRobot and any specific humanoid platform.**

Twin Runtime focuses on the layer that connects:

**Identity → Representation → Presence → Control → Enforcement → Audit**

while external ecosystems continue to provide:

**AI → Skills → Transport → Robotics → Hardware → Safety.**

The long-term goal is to enable developers, AI systems and robot providers to participate in a common ecosystem for licensed human presence without requiring a single robotics stack or humanoid manufacturer.
