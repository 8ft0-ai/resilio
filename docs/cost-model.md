# Reference Cost Model

## Constraint

The canonical public Resilio reference environment must be inexpensive enough to leave running continuously.

The current design constraint is:

- **target normal spend:** no more than US$5 per month;
- **hard engineering budget:** no more than US$10 per month under expected showcase traffic.

The budget is an architectural requirement, not an after-the-fact optimisation target.

## Design consequences

The reference deployment should favour services with ongoing free allowances or scale-to-zero characteristics and avoid permanent baseline resources whose cost is disproportionate to a low-traffic open-source environment.

The initial reference profile therefore favours:

- Cloud Run for product services;
- Pub/Sub for event transport;
- Firestore for operational state;
- BigQuery for bounded historical analytics;
- Cloud Storage for evidence artefacts;
- Cloud Build for trusted builds;
- Artifact Registry with strict retention;
- Workflows and Cloud Scheduler for bounded orchestration;
- Secret Manager and Cloud KMS for secret/key responsibilities;
- Cloud Logging and Monitoring within controlled telemetry volumes;
- one free-tier `e2-micro` VM where an independent probe is useful; and
- GKE Autopilot only for ephemeral resilience-lab workloads.

The reference profile should initially avoid:

- always-on Cloud SQL;
- permanently running GKE workloads;
- always-warm Cloud Run minimum instances;
- dedicated Redis/Memorystore;
- permanently provisioned load-balancer/security products where their fixed cost would dominate the budget;
- NAT infrastructure unless a requirement justifies it; and
- multi-region production topology in the continuously running showcase environment.

These features may still be represented in an enterprise deployment profile where the associated requirement and cost are explicit.

## Indicative normal-cost shape

At low showcase traffic, the intended shape is approximately:

```text
Cloud Run                         near $0
Firestore                         near $0
Pub/Sub                           near $0
BigQuery                          near $0
Cloud Storage                     near $0
Cloud Build                       near $0
Secret Manager / KMS              near $0
Logging / Monitoring              near $0
Compute Engine e2-micro           free-tier target
GKE management                    free-tier target
Artifact Registry                 bounded retention
GKE experiments                   short-lived usage
network/other                     small reserve
```

Actual pricing and free-tier limits are external facts that can change. Implementation work must verify current Google Cloud pricing before relying on a specific allowance.

## FinOps as an engineering control

Cost should be observable and governed like reliability or security.

Expected controls include:

- a declared monthly budget in repository policy;
- budget notifications;
- estimated infrastructure cost changes on relevant PRs where practical;
- mandatory resource labels/tags needed for attribution;
- retention policies for build artefacts, logs and evidence;
- bounded experiment runtime;
- maximum experiment cost policy;
- automatic cleanup; and
- detection of residual billable resources after experiments.

A possible policy shape is:

```yaml
reference:
  monthly_target_usd: 5
  monthly_maximum_usd: 10

experiments:
  maximum_estimated_cost_usd: 1
  maximum_runtime_minutes: 60
```

The exact schema is not yet approved implementation.

## Budget alerts are not a hard spending cap

Cloud billing alerts should be treated as detection and control input, not as proof that spending cannot exceed the budget.

The engineering system should therefore combine alerts with preventive constraints such as:

- scale-to-zero defaults;
- quotas where appropriate;
- bounded maximum instances;
- experiment TTLs;
- automatic teardown;
- limited IAM authority; and
- explicit review for changes that introduce persistent billable resources.

The system should fail safe around optional experiments when spending approaches its operational boundary rather than relying on disabling an entire billing account.

## Cost and resilience experiments

Chaos and game-day execution should be designed to remain cheap because experiment infrastructure is temporary.

An experiment should capture, before execution:

- target resources;
- expected maximum duration;
- estimated incremental cost where material; and
- cleanup deadline.

An experiment that exceeds its permitted lifetime or leaves unexpected billable resources should itself create an operational finding or incident.

## Enterprise-grade versus enterprise-sized

The reference environment is intended to be **enterprise-engineered, not enterprise-sized**.

High availability, multi-zone databases, multi-region recovery, larger minimum capacities and stronger paid security/networking products may be appropriate for a real production deployment. Resilio should document those choices without continuously purchasing them solely to make the showcase appear more enterprise-like.

Demonstrating why a control or topology is deliberately omitted from the low-cost reference profile is part of the engineering evidence.