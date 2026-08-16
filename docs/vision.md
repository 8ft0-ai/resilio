# Resilio Vision

## Purpose

Resilio is an open-source operational intelligence and resilience verification platform for cloud-native systems.

Its purpose is to help engineering teams answer, with reproducible evidence:

- what changed;
- what happened to service health;
- whether reliability objectives held;
- what failed and how the system recovered; and
- what happens when a system is deliberately subjected to controlled failure.

Resilio combines change intelligence, service reliability, incidents, controlled resilience experiments and operational evidence. It is intended to be a real open-source product rather than a demonstration application, while its own design, delivery and operation deliberately showcase enterprise-grade engineering practice.

## Product proposition

> Continuously test and prove how cloud-native systems behave under change and failure.

The platform should distinguish observed fact from derived result and inference. A resilience claim is only meaningful when it can be traced to durable evidence.

A typical Resilio experiment should be able to state:

1. the hypothesis;
2. the exact system and deployment identity under test;
3. the fault introduced;
4. the allowed blast radius;
5. the steady-state conditions expected before execution;
6. the abort conditions;
7. what actually happened;
8. whether recovery completed within the expected boundary; and
9. the evidence supporting the result.

## Core product domains

Resilio is expected to evolve around the following concepts:

- **Service** — an independently operated software capability.
- **Environment** — the runtime context in which a service operates.
- **Change** — a material modification to software, configuration or infrastructure.
- **Deployment** — a concrete release of an immutable artefact into an environment.
- **SLI/SLO** — measurable service behaviour and its reliability objective.
- **Incident** — an operational event requiring investigation or mitigation.
- **Experiment definition** — a versioned description of a resilience hypothesis and bounded fault.
- **Experiment run** — an authorised execution of an immutable experiment definition against an identified runtime state.
- **Evidence** — durable observations supporting a claim or result.

## Reliability Lab

Controlled failure experimentation is a first-class product capability, not an auxiliary demo.

Experiments should be hypothesis-driven and bounded rather than arbitrary destructive actions. Examples include:

- workload instance loss;
- dependency latency or unavailability;
- CPU or memory pressure;
- DNS or network degradation;
- Pub/Sub backlog, duplication, delayed delivery or poison messages;
- credential rotation or revocation;
- IAM denial;
- malformed or replayed webhooks;
- unsigned or tampered deployment artefacts.

Resilio should support automatic steady-state verification, fault injection, observation, abort, recovery verification and evidence capture.

## Reference workload

Resilio will include a deliberately small distributed reference workload that can be safely broken. It exists to exercise realistic failure modes without turning the project into a large sample business application.

A likely shape is:

```text
orders
  |-- inventory
  |-- payments
          |
          v
        Pub/Sub
          |
          v
    notifications
```

The reference workload should demonstrate synchronous and asynchronous dependencies, retries, timeouts, circuit breakers, distributed tracing, health states and graceful degradation.

## Self-observation

Resilio should eventually monitor and test itself.

Its own deployments should become change events. Its own services should have SLOs. Its own incidents should be recorded. Its own resilience experiments should be visible through the same evidence model offered to users.

This creates an important project property: the product is also a reference implementation of the engineering practices it promotes.

## Open-source position

Resilio is public and open source under Apache-2.0.

Google Cloud is the canonical reference deployment, but the product domain should not be coupled unnecessarily to Google Cloud concepts. Cloud-specific capabilities should be expressed through bounded adapters or deployment implementations where practical so that the core product remains understandable and extensible beyond one provider.

The project should read and behave like genuine open-source software, not a personal portfolio repository.

## Non-goals

Resilio is not intended to be:

- a generic observability vendor replacement;
- a full internal developer platform;
- an uncontrolled Chaos Monkey clone;
- a collection of Google Cloud services assembled only to maximise product coverage;
- a production-scale reference environment consuming enterprise-scale infrastructure costs; or
- a system whose security depends on configuration secrecy.

The project should demonstrate enterprise-grade engineering through proportional controls, reproducibility, security, reliability and evidence rather than through unnecessary complexity.