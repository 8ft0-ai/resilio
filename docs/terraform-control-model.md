# Terraform control model

## Status

This document describes the Phase 3 Terraform control model established under issue #14. **Slice A is an inert control seed:** the new reusable workflows are `workflow_call` only, there is no active privileged caller, no new Workload Identity Federation binding, and no cloud or Terraform-state mutation is created by landing this slice.

The governing architecture is issue #14 Gate 1 as amended and freshly approved at Gate 2. The accepted Gate 3 plan deliberately separates repository control code from later cloud authority so the exact immutable Slice A commit can become the identity pinned by subsequent callers and WIF grants.

## State and authority domains

`infra/bootstrap` remains the rare control-plane root. It retains the projects, the private state bucket, Workload Identity Federation, bootstrap APIs, budget controls and the maximum authority envelope for operational identities. Existing bootstrap resources do not move state.

`infra/foundation` is the first normal operational root. Its backend contract is bucket `resilio-control-e882d4-tfstate`, prefix `foundation`, canonical state object `foundation/default.tfstate`, lock object `foundation/default.tflock`, and private reviewed-plan evidence prefix `plan-evidence/foundation/`.

The ordinary root cannot create or broaden the identity that authorises itself. Later bootstrap slices create distinct `github-foundation-planner` and `github-foundation-applier` identities. The existing `github-federation-probe` remains an authentication proof identity only.

## Candidate boundary

Normal candidate-controlled Terraform is data, not trusted privileged code. The only candidate file for the initial proof is `infra/foundation/resources.tf.json`.

Before authentication, trusted Python code parses it using duplicate-key rejection and accepts only the empty Slice A payload `{}` or the exact future `google_service_account.phase3_terraform_sentinel` declaration approved by issue #14. The sentinel fixes the project, account ID, display name, description and `deletion_policy = "PREVENT"`. Interpolation/expression strings, provider or backend blocks, modules, data sources, outputs, provisioners, executable helpers and any other resource are rejected.

The privileged working directory is assembled from trusted `backend.tf`, `versions.tf`, `provider.tf` and `.terraform.lock.hcl` checked out from the reusable workflow's own immutable source at `job.workflow_sha`. The exact candidate JSON is fetched by candidate SHA as data and canonicalised before it is copied into that trusted directory. A privileged workflow never executes an untrusted PR checkout, action, script, provider configuration, backend configuration or module.

## Reusable workflow trust

Slice A adds three reusable workflows only: `terraform-federation-reusable.yml`, `terraform-plan-reusable.yml` and `terraform-apply-reusable.yml`. They have no direct trigger in Slice A. Later callers must invoke the exact reviewed Slice A commit SHA. Each reusable job checks out security-critical repository code from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}` with persisted checkout credentials disabled.

The planner and applier use dedicated service-account identities. WIF bindings are not created by Slice A; later bootstrap authority binds each service account to the corresponding immutable reusable workflow identity while preserving the existing Resilio/main trust condition. Capability therefore does not become authority merely because a reusable workflow exists.

## Plan evidence and apply interlock

A PR plan is review evidence, not the binary plan later applied. The trusted planner validates an exact open same-repository PR/head/base, accepts only the governed candidate file, records exact configuration/provider/state identities, keeps saved plan/state/`terraform show -json` private and ephemeral, stores a private canonical full-material-effect record in the private state bucket, and emits only a sanitised public manifest containing identity/digests plus resource address/action summaries, policy result and cost classification.

The private representation includes before/after semantics, unknown-value structure, sensitive markers, replacement paths, outputs and other material effect structure. It is never emitted to the public log.

For apply, the trusted workflow proves current protected `main`, the merged PR and reviewed head, fetches both reviewed-head and merged-main `resources.tf.json`, and requires their canonical bytes to match. It then creates a **fresh plan from the merged-main configuration** and current remote state. The current private effect must match the reviewed private effect exactly, including state lineage/serial/object generation and every material plan field. Any mismatch is fail-closed; only the fresh saved plan generated in that same trusted job may be applied.

## Initial state hand-off

A read-only planner must not create the first state object. A later, separately reviewed temporary main-only setup caller will invoke the applier reusable workflow in `initialise-empty-state` mode exactly once. That mode requires `foundation/default.tfstate` to be absent, uses normal backend locking, allows creation only of an empty initial state, and fails if any managed resource is present. Planner activation occurs only after that hand-off succeeds. No `-lock=false` or routine `force-unlock` path is part of the control model.

## Policy, cost and drift

For the initial proof, the strict candidate grammar is also the minimum policy surface: unknown resources and unknown cost classes are impossible to pass. The sentinel is classified `known-negligible/control-plane`; this does not weaken Resilio's normal US$5/month target or US$10/month engineering ceiling.

Later active callers use root-scoped non-cancelling, lossless queueing plus backend locking and freshness guards. Weekly/manual drift uses planner authority, never calls `apply`, and produces deduplicated evidence for governed reconciliation rather than silently overwriting unexpected state.

## Security and evidence rules

- no long-lived Google Cloud service-account keys;
- no raw state, saved plan or unsanitised plan JSON in Git or public workflow evidence;
- no bootstrap-state content access for foundation automation;
- no planner mutation authority and no planner ability to impersonate the applier;
- no applier authority to administer project IAM, create service-account keys or delete the protected sentinel;
- generated WIF credential files are ephemeral and removed;
- private effect evidence is write-once by exact PR/head object identity;
- stale PR, current-main, configuration, state or effect identity stops before apply;
- partial apply or drift is evidence for governed recovery, not authority for automatic rollback.

## Slice A validation

Repository validation remains credential-free. It verifies the closed foundation contract, action pins, callable-only reusable workflow surface, strict candidate grammar, canonical effect logic, secret/state filename exclusions and Terraform formatting/init-without-backend/validation for both roots.

Landing Slice A creates **no cloud authority**. The resulting protected-main commit is the immutable control-seed identity required before Slice B can migrate the existing federation proof to the reusable authentication path.
