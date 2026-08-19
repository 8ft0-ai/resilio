# Terraform control model

This document records the repository implementation of Resilio issue #14 Phase 3. The initial implementation is intentionally narrow: it proves the governed Terraform control path before later phases add product runtime.

## Current status

Slice A is a **repository-only control seed**. It adds the foundation Terraform root, trusted reusable workflow code, validation, tests and evidence helpers, but it activates no cloud caller and grants no new Google Cloud authority. All new privileged workflow definitions are `workflow_call` only. The existing `federation-smoke.yml` remains the only current cloud workflow until later reviewed slices activate callers.

## Root and state boundary

`infra/bootstrap` remains the rare control-plane root that owns the projects, private state bucket, Workload Identity Federation and authority-establishing IAM. `infra/foundation` is the first normal Git-driven operational root.

The foundation backend reuses the private, versioned `resilio-control-e882d4-tfstate` bucket with prefix `foundation`; the canonical state object is `foundation/default.tfstate`. No bootstrap resource changes state ownership, and foundation does not use `terraform_remote_state` to read bootstrap state.

## Candidate configuration contract

Credential-bearing jobs construct a fresh Terraform directory from trusted `backend.tf`, `versions.tf`, `provider.tf` and `.terraform.lock.hcl`. Candidate-controlled Terraform is exactly `infra/foundation/resources.tf.json`, parsed as strict JSON with duplicate-key rejection before authentication.

The Slice A baseline is empty. The later end-to-end proof may change only to the exact allowed `google_service_account.phase3_terraform_sentinel` resource for `phase3-terraform-sentinel` in `resilio-reference-e882d4`, with literal values, provider-native `deletion_policy = "PREVENT"` and Terraform `prevent_destroy = true`. Modules, data sources, outputs, provider/backend blocks, provisioners, interpolation expressions and other resource types are outside the initial grammar. Expanding the grammar requires a separately reviewed control-plane change.

## Trusted workflow source and identity

The reusable planner and applier check out security-critical code from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}`. Candidate `resources.tf.json` is fetched separately as data by exact GitHub commit/blob identity, validated before authentication and copied into the trusted working directory. Candidate workflows, actions, scripts, modules, provider configuration and backend configuration are never executed in the privileged boundary.

Planner and applier share the `terraform-foundation` concurrency group with `queue: max` and `cancel-in-progress: false`. Terraform GCS locking remains the state-safety mechanism; GitHub queueing is an additional orchestration control.

Later slices create distinct `github-foundation-planner` and `github-foundation-applier` service accounts and bind each only to its own immutable reusable-workflow identity while retaining the existing immutable Resilio/main Workload Identity Federation condition. The existing `github-federation-probe` remains authentication proof only. No long-lived Google Cloud service-account keys are permitted.

## Plan evidence and apply interlock

Raw Terraform state, saved plans and `terraform show -json` output are private. A live PR plan later stores **private plan evidence** under `plan-evidence/foundation/`, including exact state identity and a canonical full material-effect representation. The canonicaliser binds the complete resource-change object, including the singleton resource index and change semantics such as before/after values, unknown/sensitive markers and replacement paths. It fails closed rather than silently reducing plans that contain resource drift, deferred changes, incomplete planning, action invocations, unknown plan structures, outputs or resource classes outside the initial foundation contract.

Public evidence exposes only non-sensitive identity and review material: PR/base/head, the immutable control seed SHA, root/backend namespace, configuration/provider digests, hashed state lineage, state serial/object generation, resource addresses/actions, policy/cost results and effect/manifest digests. The private evidence embeds the same public identity record alongside the full private effect and exact state identity.

The reviewed PR plan is evidence, not a binary artefact applied later. After authorised merge, the trusted applier produces a fresh plan from exact current `main`, requires the reviewed state identity and immutable control seed identity to remain current, compares the complete private effect and applies only that freshly generated saved plan from the same job. Any state-generation, control-seed or material-effect mismatch fails closed.

## Initial state, drift and cost

A later one-time setup slice proves `foundation/default.tfstate` is absent, initialises the empty remote state and records its non-sensitive identity before live planning is enabled. Planner authority does not include routine state-object writes.

Drift reconciliation later runs weekly and on manual request using the read-only planner identity. It may surface a deduplicated evidence-backed issue but never calls `terraform apply` or automatically adopts unexpected cloud state.

The first policy contract fails closed on unknown resource/configuration classes and permits only the empty baseline plus the eventual exact sentinel proof. The cost authority remains the repository target of at most US$5/month and engineering ceiling of US$10/month; the billing budget is detection evidence, not a hard cap.

## Recovery

Before the bootstrap authority slice, Phase 3 changes are repository-only and can be reverted normally. After authority exists, stale/mismatched plans do not apply, partial operations do not trigger automatic rollback or state forcing, `force-unlock` requires proof of a stale lock, and emergency authority revocation removes planner/applier federation bindings before IAM is reconciled through reviewed bootstrap Terraform.

Issue #14 remains the governing architecture, sequencing and authority record. This document is an implementation reference, not a substitute for refreshing primary GitHub/workflow evidence before consequential actions.
