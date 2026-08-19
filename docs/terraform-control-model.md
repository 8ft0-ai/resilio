# Terraform control model

## Status

Issue #14 establishes Resilio's Phase 3 Terraform control model. Slice A landed the inert reusable-workflow/control seed at immutable commit `cbfe9821ec07ca6c0c869ebe75100bc500c92a04`. Slice B then migrated the existing manual federation proof to that immutable reusable authentication path and passed the required post-merge smoke from protected `main`.

Slice C declares the bootstrap-owned planner/applier authority envelope in Terraform. **Landing Slice C alone does not activate that authority.** The exact repository candidate must be validated, freshly reviewed and merged before one separately governed owner-local bootstrap plan/apply may change WIF/IAM/Storage authority. The resulting cloud state and immediate regression smoke must then be reconciled before any foundation-state initialisation.

The governing architecture is issue #14 Gate 1 as amended and freshly approved at Gate 2. The accepted Gate 3 plan deliberately separates immutable trusted workflow code, bootstrap-owned maximum authority, operational state initialisation and later active orchestration.

## State and authority domains

`infra/bootstrap` remains the rare control-plane root. It retains the projects, private state bucket, Workload Identity Federation, bootstrap APIs, budget controls and maximum authority envelope for operational identities. Existing bootstrap resources do not move state.

`infra/foundation` is the first normal operational root. Its backend contract is bucket `resilio-control-e882d4-tfstate`, prefix `foundation`, canonical state object `foundation/default.tfstate`, lock object `foundation/default.tflock`, and private reviewed-plan evidence prefix `plan-evidence/foundation/`.

The ordinary root cannot create or broaden the identity that authorises itself. Bootstrap owns distinct `github-foundation-planner` and `github-foundation-applier` identities and their maximum IAM/state authority. The existing `github-federation-probe` remains an authentication proof identity only.

## Candidate boundary

Normal candidate-controlled Terraform is data, not trusted privileged code. The only candidate file for the initial proof is `infra/foundation/resources.tf.json`.

Before authentication, trusted Python code parses it using duplicate-key rejection and accepts only the empty payload used before activation or the exact future `google_service_account.phase3_terraform_sentinel` declaration approved by issue #14. The sentinel fixes the project, account ID, display name, description and `deletion_policy = "PREVENT"`. Interpolation/expression strings, provider or backend blocks, modules, data sources, outputs, provisioners, executable helpers and any other resource are rejected.

The privileged working directory is assembled from trusted `backend.tf`, `versions.tf`, `provider.tf` and `.terraform.lock.hcl` checked out from the reusable workflow's own immutable source at `job.workflow_sha`. The exact candidate JSON is fetched by candidate SHA as data and canonicalised before it is copied into that trusted directory. A privileged workflow never executes an untrusted PR checkout, action, script, provider configuration, backend configuration or module.

## Reusable workflow trust

The control seed contains exactly three reusable workflows: `terraform-federation-reusable.yml`, `terraform-plan-reusable.yml` and `terraform-apply-reusable.yml`. They remain `workflow_call`-only entry points. Their presence in Git creates **no cloud authority**; cloud capability exists only after a separately governed WIF/IAM binding is activated. Credential-bearing callers invoke the workflows by the immutable control-seed SHA. Each reusable job checks out security-critical repository code from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}` with persisted checkout credentials disabled.

Slice B proved this binding operationally: the manual `federation-smoke.yml` on protected `main` called `terraform-federation-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`, used the unchanged `github-federation-probe` service account and obtained the intended 300-second token without resource mutation.

## Workload Identity Federation authority

The shared GitHub WIF provider continues to require the immutable Resilio `refs/heads/main` subject:

```text
repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main
```

Slice C desired state preserves `google.subject = assertion.sub` and adds mappings for `assertion.job_workflow_ref` and `assertion.job_workflow_sha`. It does not create a duplicate provider or broaden the provider's subject condition.

The existing probe binding remains unchanged in authority. Planner/applier bindings are narrower: each service account may be impersonated only through a `principalSet` whose `attribute.job_workflow_ref` equals its corresponding reusable workflow at the immutable control-seed SHA:

- `github-foundation-planner` → `terraform-plan-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`;
- `github-foundation-applier` → `terraform-apply-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`.

The provider-level repository/main condition still applies independently. Candidate-controlled code therefore cannot mint planner/applier authority merely by naming these identities.

## Planner and applier resource authority

The planner's reference-project custom role contains only:

- `iam.serviceAccounts.get`;
- `iam.serviceAccountKeys.list`;
- `iam.serviceAccounts.getIamPolicy`; and
- `resourcemanager.projects.getIamPolicy`.

This is read/verification authority for the initial service-account proof only. The planner cannot mutate the sentinel or project IAM.

The applier's reference-project custom role contains only:

- `iam.serviceAccounts.create`;
- `iam.serviceAccounts.get`; and
- `iam.serviceAccounts.update`.

It excludes service-account deletion, key operations, `setIamPolicy`, `actAs`, token creation and project IAM mutation. No Owner/Editor/admin role is used.

## Foundation state and private evidence authority

Cloud Storage permissions are split so backend discovery does not imply bucket-wide data access.

Both planner and applier receive a list-only custom role with `storage.objects.list` on the state bucket because Terraform 1.15.8's GCS backend enumerates workspaces under its prefix. Read authority uses a separate `storage.objects.get` role conditioned to the exact `foundation/default.tfstate` object.

Normal Terraform backend locking is permitted only for `foundation/default.tflock`, through a custom role containing `storage.objects.create`, `storage.objects.get` and `storage.objects.delete`. This is the minimum operation set required by the pinned GCS backend to create the lock exclusively, inspect it on contention and delete it by matching generation.

Only the applier receives state-write authority for `foundation/default.tfstate`, containing `storage.objects.create` and `storage.objects.delete`. Those permissions are required by Cloud Storage object replacement semantics; the planner never receives them for the state object.

Private reviewed-plan evidence is separate again. The planner receives `storage.objects.create` only, conditioned to `plan-evidence/foundation/`; trusted code uses `ifGenerationMatch=0`, so an existing evidence object cannot be overwritten. The applier receives only `storage.objects.get` on that prefix. Neither identity receives bootstrap-state content access or broad Storage administrative roles.

## Plan evidence and apply interlock

A PR plan is review evidence, not the binary plan later applied. The trusted planner validates an exact open same-repository PR/head/base, accepts only the governed candidate file, records exact configuration/provider/state identities, keeps saved plan/state/`terraform show -json` private and ephemeral, stores a private canonical full-material-effect record in the private state bucket, and emits only a sanitised public manifest containing identity/digests plus resource address/action summaries, policy result and cost classification.

The private representation includes before/after semantics, unknown-value structure, sensitive markers, replacement paths, outputs and other material effect structure. It is never emitted to the public log.

For apply, the trusted workflow proves current protected `main`, the merged PR and reviewed head, fetches both reviewed-head and merged-main `resources.tf.json`, and requires their canonical bytes to match. It then creates a **fresh plan from the merged-main configuration** and current remote state. The current private effect must match the reviewed private effect exactly, including state lineage/serial/object generation and every material plan field. Any mismatch is fail-closed; only the fresh saved plan generated in that same trusted job may be applied.

## Slice C activation boundary

The repository declaration of planner/applier identities and IAM grants is not itself cloud evidence. After Slice C receives exact-candidate validation, fresh review and merge, one owner-local bootstrap operation activates the envelope because the Phase 2 control plane deliberately lacks an automation identity allowed to broaden its own authority.

That operation must use the existing remote `bootstrap` state, produce a full reviewed-main plan, reject any effect outside the expected WIF claim mapping/service accounts/custom roles/bindings, apply without `-target`, record sanitised resulting-state evidence and prove a subsequent no-change plan. The existing federation smoke is then rerun immediately. A smoke regression stops the Phase 3 sequence before foundation state is created.

## Initial state hand-off

A read-only planner must not create the first state object. A later, separately reviewed temporary main-only setup caller invokes the applier reusable workflow in `initialise-empty-state` mode exactly once. That mode requires `foundation/default.tfstate` to be absent, uses normal backend locking, allows creation only of an empty initial state, and fails if any managed resource is present. Planner activation occurs only after that hand-off succeeds. No `-lock=false` or routine `force-unlock` path is part of the control model.

## Policy, cost and drift

For the initial proof, the strict candidate grammar is also the minimum policy surface: unknown resources and unknown cost classes cannot pass. The sentinel is classified `known-negligible/control-plane`; this does not weaken Resilio's normal US$5/month target or US$10/month engineering ceiling.

Later active callers use root-scoped non-cancelling, lossless queueing plus backend locking and freshness guards. Weekly/manual drift uses planner authority, never calls `apply`, and produces deduplicated evidence for governed reconciliation rather than silently overwriting unexpected state.

## Security and evidence rules

- no long-lived Google Cloud service-account keys;
- no raw state, saved plan or unsanitised plan JSON in Git or public workflow evidence;
- no bootstrap-state content access for foundation automation;
- no planner state/resource mutation authority beyond the exact ephemeral lock and create-only private evidence object contract;
- no planner ability to impersonate the applier;
- no applier authority to administer project IAM, create service-account keys or delete the protected sentinel;
- generated WIF credential files are ephemeral and removed;
- private effect evidence is write-once by exact PR/head object identity;
- stale PR, current-main, configuration, state or effect identity stops before apply;
- partial apply or drift is evidence for governed recovery, not authority for automatic rollback.

## Repository validation

Repository validation remains credential-free. It verifies the closed foundation contract, immutable action/workflow pins, strict candidate grammar, canonical effect logic, secret/state filename exclusions, exact bootstrap/WIF authority-envelope constraints, forbidden broad roles/permissions and Terraform formatting/init-without-backend/validation for both roots.

No repository validation job performs WIF authentication, live-state planning or cloud mutation.
