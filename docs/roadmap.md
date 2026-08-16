# Resilio Delivery Roadmap

This roadmap records the current intended sequencing. It is deliberately capability-oriented rather than a fixed backlog. Later phases should be refined only when earlier evidence makes them safely decidable.

## M0 — Resilio can change itself safely

The first meaningful milestone is not application functionality. It is a governed engineering system capable of proposing, validating, approving, building, deploying and verifying a minimal change through Git with short-lived identity, private remote state, auditable evidence and the cost constraint intact.

## Phase 0 — Engineering foundation

Establish the repository operating model before application code.

Expected outcomes:

- public monorepo structure grows from real artefacts rather than empty scaffolding;
- product vision and architectural direction documented;
- contribution, security and governance expectations established;
- initial ADR process established;
- GitHub issue/PR conventions defined;
- baseline documentation-as-code checks identified.

## Phase 1 — Repository governance and baseline CI

Expected outcomes:

- protected `main` and PR-driven change flow;
- required mechanical checks;
- secret scanning and dependency hygiene;
- Terraform syntax/format validation when IaC appears;
- path-aware validation so unrelated changes do not trigger unnecessary work;
- proportional ownership/review rules.

## Phase 2 — GCP bootstrap

Create the minimum control-plane resources required for Git-driven operation.

Expected outcomes:

- canonical control/reference project model validated;
- remote private GCS Terraform state;
- GitHub-to-GCP Workload Identity Federation;
- no long-lived Google Cloud service-account keys;
- bounded IAM;
- initial billing/cost controls;
- bootstrap state migrated remotely and local state removed.

## Phase 3 — Terraform control model

Expected outcomes:

- bounded Terraform roots/state domains;
- plan-on-PR and apply-after-authorised-merge;
- private/versioned/auditable state;
- drift detection;
- policy and cost validation;
- minimal inter-state coupling.

## Phase 4 — Trusted software supply chain

Expected outcomes:

- GitHub remains the initiating governance/orchestration plane;
- Cloud Build produces immutable artefacts;
- tests, SBOM, vulnerability checks and provenance are captured;
- artefacts are stored by digest in Artifact Registry;
- deployment promotes the same artefact rather than rebuilding;
- first Cloud Run service deploys and is independently verified.

## Phase 5 — First product vertical slice

Implement the smallest useful Resilio flow:

```text
deployment/change event
        |
        v
Cloud Run ingestion
        |
        v
Pub/Sub
        |
        v
processor
        |
        v
operational state
        |
        v
API/UI
```

Initial domain focus:

- Service;
- Environment;
- Change;
- Deployment; and
- Evidence.

The objective is to prove immutable change/deployment identity and evidence before adding broader operational features.

## Phase 6 — Observability and SRE

Expected outcomes:

- OpenTelemetry-based logs, metrics and traces;
- service health/readiness contracts;
- versioned SLI/SLO definitions in Git;
- alerts linked to runbooks;
- independent synthetic probe where justified;
- Resilio begins observing its own runtime behaviour.

## Phase 7 — Incidents and operational evidence

Expected outcomes:

- incident domain model;
- SLO breach and evidence correlation;
- durable operational evidence;
- evidence-backed GitHub incident/issues where appropriate;
- links between deployments, health impact, incidents and actions.

## Phase 8 — Reference distributed workload

Build the smallest credible system that can be deliberately broken.

Expected characteristics:

- synchronous service dependency;
- asynchronous Pub/Sub dependency;
- retries and timeouts;
- circuit-breaker/degraded behaviour;
- tracing and health states;
- enough complexity for realistic resilience experiments without becoming the product focus.

## Phase 9 — Resilience experiment model

Introduce versioned experiment definitions and runs.

Expected model:

- hypothesis;
- exact target/deployment identity;
- steady-state conditions;
- fault;
- blast radius;
- abort conditions;
- recovery conditions;
- evidence requirements; and
- result.

Initial experiments should favour serverless/application and event-system failure modes before Kubernetes-specific faults.

## Phase 10 — IssueOps experiment execution

Expected outcomes:

- Git defines which experiment definitions are authorised;
- IssueOps requests a particular run;
- automation validates caller, target, revision, budget, blast radius and steady state;
- execution, abort, recovery, evidence capture and result publication are automated;
- operational runs do not require mutable experiment definitions.

## Phase 11 — Ephemeral GKE resilience lab

Expected outcomes:

- GKE Autopilot used only when infrastructure-level failure modes justify it;
- reference workloads normally absent/scaled down;
- experiments activate bounded workloads;
- pod/replica/resource/network/DNS/deployment failures can be exercised;
- TTL, cost and cleanup are enforced;
- residual billable resources are independently checked.

## Phase 12 — Analytics and operational intelligence

Expected outcomes:

- historical events/observations flow to BigQuery;
- useful queries correlate change, incidents, SLO impact and experiment outcomes;
- analytics remain evidence-backed rather than arbitrary scoring;
- Cloud Storage retains suitable immutable evidence artefacts.

## Phase 13 — Security resilience

Extend controlled failure beyond availability.

Candidate scenarios include:

- invalid or replayed webhook signatures;
- expired/revoked credentials;
- secret rotation;
- IAM denial;
- malformed JWTs;
- tampered or unsigned artefacts; and
- unexpected workload identity.

Correct behaviour may be denial/fail-closed rather than continued availability.

## Phase 14 — Game Days

Compose experiments into repeatable scenarios that produce aggregate operational evidence, incidents and follow-up engineering actions.

Game Days should demonstrate not only failure injection but learning and measurable reliability improvement across repeated executions.

## Phase 15 — Public OSS hardening and V1 readiness

Expected outcomes include:

- strong contributor experience;
- local development path using containers/emulators/test doubles;
- architecture, API and schema documentation;
- compatibility and release policy;
- security disclosure process;
- automated release evidence;
- deployable reference profile;
- documented enterprise deployment profile;
- recovery and cost documentation; and
- evidence that a third party can deploy Resilio without knowledge of the canonical maintainer environment.

## Sequencing rule

Do not create a large speculative backlog for distant phases. Refine the next bounded phase when the current phase has produced enough evidence to make the next design decision responsibly.

Every new capability should be built using the engineering controls established before it, rather than adding delivery, security, SRE or documentation practices retrospectively.