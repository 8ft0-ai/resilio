# Resilio

Open-source operational intelligence and resilience verification for cloud-native systems.

Resilio is intended to help engineering teams understand what changed, what happened to service health, whether reliability objectives held, how systems recover from failure, and what evidence supports those conclusions.

A central product capability is a controlled **Reliability Lab**: versioned, hypothesis-driven resilience experiments with explicit blast radius, abort conditions, recovery criteria and durable evidence. Resilio is intended to observe and eventually test itself as part of its canonical reference deployment.

## Engineering intent

Resilio is being developed as a real open-source product and as a reference implementation of enterprise-grade engineering practice. Its engineering model is deliberately Git-driven:

- Git is authoritative for desired state;
- GitHub provides governance and operational intent;
- cloud changes are reconciled through automation rather than routine console mutation;
- long-lived Google Cloud credentials are avoided;
- Terraform state and secret material remain private and outside Git;
- the public reference environment is designed to remain within a US$10/month engineering budget; and
- enterprise-grade controls are applied proportionally rather than by reproducing enterprise-scale infrastructure for its own sake.

Google Cloud is the canonical reference deployment, but the Resilio product model should remain independent of unnecessary provider-specific assumptions.

## Design documentation

The project is currently in its design/foundation stage. The discussions and decisions that define the initial direction are captured in:

- [Vision](docs/vision.md)
- [Architecture direction](docs/architecture.md)
- [Git-driven engineering model](docs/engineering-model.md)
- [Security and private-state boundary](docs/security-and-private-state.md)
- [Reference cost model](docs/cost-model.md)
- [Delivery roadmap](docs/roadmap.md)

The first meaningful engineering milestone is **M0 — Resilio can change itself safely**: a governed path from authorised Git change through build, deployment and verification using short-lived identity, private remote state, auditable evidence and the declared cost constraint.

## Status

Early design. No production or reference deployment has been established yet.

## Licence

Apache License 2.0. See [LICENSE](LICENSE).