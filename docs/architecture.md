# Resilio Architecture Direction

## Architectural intent

Resilio should demonstrate enterprise-grade engineering while keeping its continuously running reference environment inside a deliberately small cost envelope.

The architecture therefore favours serverless and scale-to-zero services for the product plane, with Kubernetes reserved for controlled resilience experiments where infrastructure-level failure modes justify it.

## Reference architecture

```text
                         GitHub
                    authoritative state
                           |
          +----------------+----------------+
          |                |                |
       Issues             PRs            Releases
       intent          desired state      identity
          |                |                |
          +----------------+----------------+
                           |
                    GitHub Actions
               governance / orchestration
                           |
                   OIDC / federation
                           |
                           v
                  GCP CONTROL PLANE
           Terraform / Build / Deploy
                           |
                           v
                   REFERENCE PLATFORM
       +---------------+---+----+----------------+
       |               |        |                |
       v               v        v                v
   Cloud Run        Pub/Sub  Firestore        BigQuery
       |                                            |
       +--------------------+-----------------------+
                            |
                            v
                     Evidence storage

                            |
                            v
                    RESILIENCE LAB
                     GKE Autopilot
                  normally scaled down
                            |
                            v
                   controlled failures
```

Supporting capabilities are expected to include Cloud Storage, Workflows, Cloud Scheduler, Secret Manager, Cloud KMS, Cloud Logging, Cloud Monitoring, OpenTelemetry, Artifact Registry and suitable software supply-chain controls.

These services should only be introduced when a product or engineering requirement justifies them.

## Control plane and workload plane

The preferred reference deployment uses two Google Cloud projects:

```text
control project
  - Terraform state
  - GitHub workload identity federation
  - deployment/control identities
  - control-plane resources

reference project
  - Resilio application services
  - event and data services
  - observability
  - reference workload
  - resilience lab
```

This separation provides a useful security boundary: compromise of an application workload should not grant access to Terraform state or deployment authority.

The exact project layout remains subject to implementation design and cost validation.

## Serverless-first runtime

Cloud Run is the preferred runtime for Resilio services because low-traffic services can scale to zero while retaining independent deployment, identity, observability and service boundaries.

Likely service responsibilities include:

- web/API;
- event ingestion;
- event normalisation and processing;
- experiment control;
- SLO evaluation;
- incident processing; and
- evidence processing.

Service decomposition should follow actual domain and authority boundaries rather than creating microservices for their own sake.

## Data responsibilities

The reference architecture should separate data by responsibility:

```text
Firestore
  operational/domain state

BigQuery
  historical events, observations and analytics

Cloud Storage
  durable evidence artefacts
```

An always-on relational database is intentionally excluded from the initial reference environment because it would materially increase baseline cost. A production deployment profile may document or implement alternative persistence topologies where justified.

## Kubernetes resilience lab

GKE Autopilot should not host permanently running product workloads in the low-cost reference profile.

Instead, it provides an ephemeral resilience laboratory for failure modes that are best exercised against Kubernetes workloads, including:

- pod termination;
- replica loss;
- CPU or memory pressure;
- DNS failure;
- network latency or loss;
- dependency blackholing;
- readiness/liveness failure; and
- bad rollout behaviour.

Experiment workloads must have bounded runtime, explicit cost limits, automatic cleanup and independent verification that billable workloads have been removed.

## Independent synthetic probe

The ongoing free-tier `e2-micro` Compute Engine allowance may be used for an independent synthetic probe or telemetry agent rather than to host the application itself.

This creates an independently failing observer and allows the project to exercise VM hardening, workload identity, monitoring and monitoring-system failure scenarios without adding normal baseline compute cost.

## Deployment profiles

Resilio should distinguish engineering requirements from deployment scale.

Expected profiles are:

### Local

Developer-oriented local runtime using containers, emulators and test doubles where practical.

### Reference

The continuously running public open-source deployment. It is enterprise-engineered but deliberately low scale and constrained to the project cost budget.

### Enterprise

A production-oriented architecture profile documenting or implementing stronger availability, isolation, recovery and scale characteristics. It need not run continuously as part of the public project.

This distinction prevents the reference environment from wasting money merely to imitate enterprise traffic volumes.

## Architectural principles

The following principles should guide subsequent decisions:

1. **Evidence before inference.** Observed fact, derived result and heuristic inference must be distinguishable.
2. **Everything important has identity.** Commits, artefacts, deployments, experiments, incidents and evidence should be immutably identifiable.
3. **Build once, promote the same artefact.** Promotion must not rebuild source.
4. **Failures are first-class behaviour.** Failure handling is designed and tested rather than added after the happy path.
5. **Fail closed where authority or integrity matters.**
6. **Idempotency and safe replay are defaults for event processing.**
7. **Observability is part of the service contract.**
8. **Infrastructure must be reproducible.**
9. **No permanent cloud credentials.**
10. **Chaos is bounded.** Experiments require blast-radius, abort and recovery constraints.
11. **No resilience claim without reproducible evidence.**
12. **Controls are proportional to risk.** Enterprise-grade engineering does not require unnecessary enterprise-scale process or infrastructure.
