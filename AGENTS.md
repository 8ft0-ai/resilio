# Repository operating contract

This file defines repository-local operating expectations for contributors and engineering agents working in Resilio.

## Authority and evidence

- Git is authoritative for desired state where state can reasonably be represented declaratively.
- GitHub issues, pull requests, reviews and repository records provide governance and operational intent.
- Capability is not authority. Access to mutate the repository, GitHub settings or cloud resources does not itself authorise that action.
- Treat stale summaries and handovers as navigation aids. Refresh decision-critical state before consequential actions.
- Prefer evidence from the exact candidate, commit, workflow run or runtime state being judged.
- Fail closed when required authority or decision-critical evidence cannot be established: do not perform the consequential mutation, and surface the unresolved boundary instead of inferring permission or state.

## Change discipline

- Work from a bounded governing issue or other explicit authority record when a change is consequential.
- Prefer the minimum safe change that satisfies the current objective.
- Do not expand a task into adjacent implementation merely because it appears useful.
- Preserve security, cost, evidence and lifecycle boundaries already established by accepted repository records.
- Keep secrets, credentials and private Terraform state out of Git.
- Do not introduce long-lived Google Cloud service-account keys.

## Autonomous progression

Routine planning, implementation, validation, bounded remediation and evidence capture should proceed without repeated human confirmation when current authority and evidence make the next action safely decidable.

Escalate only when a genuine human decision or authority boundary is reached, including material scope or architecture changes, permission broadening, security weakening, destructive or production actions, material cost commitments, or acceptance of a known failed control.

## Review independence

When a governing issue requires a genuinely fresh independent substantive review, the authoring context must not substitute its own conclusion for that review. A fresh reviewer must reconstruct the exact candidate and decision-critical evidence directly.

A review disposition does not by itself grant merge authority unless the governing record explicitly says so.

## Validation

- Run repository-owned mechanical validation before requesting substantive review.
- Validation must be reproducible and tied to the exact candidate revision where practical.
- Do not weaken tests, checks or acceptance criteria merely to obtain a passing result.
- A bounded defect with an objectively clear minimum-safe fix may be remediated within the existing scope; materially changed candidates still require any review gates applicable to the new revision.

## Cloud and runtime boundaries

Repository work must preserve the foundation documented in `docs/`:

- serverless/scale-to-zero reference architecture by default;
- private remote Terraform state split by bounded lifecycle/authority domains;
- secrets outside Git and normally outside Terraform state;
- short-lived federated identity for GitHub-to-Google Cloud access;
- normal reference-cost target of at most US$5/month and engineering ceiling of US$10/month;
- GKE Autopilot reserved for bounded ephemeral resilience experiments unless a later accepted decision changes that direction.

## Break glass

Manual emergency mutation is exceptional. It must be narrowly scoped, auditable and subsequently reconciled to authorised Git state or explicitly reversed.
