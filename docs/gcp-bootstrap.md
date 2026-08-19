# GCP bootstrap control boundary

Issue #6 established Resilio's first Google Cloud control plane. Issue #14 Phase 3 extends that bootstrap-owned control plane with the bounded authority envelope required for normal Terraform planning and apply. This document describes repository-owned desired state and execution boundaries; repository content alone is not evidence that a cloud mutation has occurred.

## Intended final state

The canonical reference deployment uses two projects:

- a **control project** for Terraform state, Workload Identity Federation and narrowly scoped GitHub automation identities; and
- a **reference project** that establishes the workload-plane boundary while remaining free of Phase 4/5 product runtime.

The project IDs are non-secret owner-supplied execution inputs. The billing-account ID and any real local variable values remain owner-local and must not be committed.

The bootstrap Terraform root is [`../infra/bootstrap`](../infra/bootstrap). It remains intentionally limited to project/control resources that establish or protect private state, keyless GitHub identity, cost detection and the maximum authority envelope for the operational `foundation` root.

## Tooling and validation

Terraform is pinned by `.terraform-version` to `1.15.8`. The root constrains `hashicorp/google` to `~> 7.42.0`, and `infra/bootstrap/.terraform.lock.hcl` records the selected provider and integrity hashes produced by Terraform itself.

The required `repository` GitHub check remains credential-free. It:

1. runs repository and cloud-bootstrap invariant validation;
2. checks Terraform formatting;
3. runs `terraform init -backend=false -lockfile=readonly`; and
4. runs `terraform validate`.

The pull-request workflow has only `contents: read`. It does not request `id-token: write`, consume GCP credentials or execute `terraform plan` against live cloud state.

## Project creation modes

Google Cloud project creation has an unavoidable environment-dependent bootstrap boundary. The approved issue #6 amendment therefore defines two explicit modes.

### Existing organisation or folder

Use `project_creation_mode = "managed-parent"` with an existing authorised `organization` or `folder` parent.

Before any mutation, read the effective `constraints/compute.skipDefaultNetworkCreation` policy. Do not create or broaden an organisation policy merely to satisfy this repository.

If that policy already prevents default-network creation, leave `remove_default_network = false`.

### No suitable parent

Use `project_creation_mode = "precreated-import"` with `project_parent_type = "none"` and no parent ID.

The two approved project IDs must first be created owner-locally with short-lived owner credentials and linked to billing. Import both projects into this Terraform root **before** the authoritative full plan. Terraform must not be allowed to attempt parentless project creation itself.

If Google creates a default VPC, set `remove_default_network = true` for the cleanup apply. The Google provider may temporarily enable `compute.googleapis.com` to remove that network. That is an explicit bootstrap side effect, not an approved final capability.

Before accepting the bootstrap:

- verify no VPC network created by this slice remains in either project;
- disable `compute.googleapis.com` again where it was enabled only for cleanup; and
- record the final enabled-service list.

Do not retain a default network or Compute Engine API merely because the provider used them during bootstrap.

## Bootstrap resources

The bootstrap root owns only control-plane resources whose lifecycle or authority boundary justifies remaining outside ordinary operational Terraform. It declares:

- the control and reference projects;
- these control-project services:
  - `billingbudgets.googleapis.com`;
  - `cloudbilling.googleapis.com`;
  - `cloudresourcemanager.googleapis.com`;
  - `iam.googleapis.com`;
  - `iamcredentials.googleapis.com`;
  - `serviceusage.googleapis.com`;
  - `storage.googleapis.com`; and
  - `sts.googleapis.com`;
- one private Terraform-state Cloud Storage bucket;
- one Workload Identity Pool and GitHub OIDC provider;
- the authentication-only `github-federation-probe` service account and its existing impersonation binding;
- distinct `github-foundation-planner` and `github-foundation-applier` service accounts;
- narrow custom IAM roles and conditional bindings that cap planner/applier state, evidence and reference-project authority; and
- one monthly billing budget covering the two projects.

Cloud Run, Pub/Sub, Firestore, BigQuery, Cloud Build, Artifact Registry, GKE and other product/runtime services remain outside this bootstrap authority slice.

## Terraform state

The state bucket is regional Standard storage in `US-CENTRAL1` and must have:

- public access prevention enforced;
- uniform bucket-level access;
- object versioning;
- `force_destroy = false`;
- Terraform `prevent_destroy`; and
- Google-managed encryption for this control plane.

The normal bucket name is `<control-project-id>-tfstate`. If that globally unique name is unavailable, stop and record an explicitly approved non-secret suffix rather than silently generating a canonical name.

The bootstrap root itself uses the canonical GCS prefix `bootstrap`. Phase 3 adds the separate operational prefix `foundation` without moving any existing bootstrap resource between states.

Planner/applier Cloud Storage access is deliberately split rather than granting Object Admin:

- both identities may list bucket objects only because Terraform's GCS backend discovers workspaces by listing the configured prefix;
- state reads are conditioned to `foundation/default.tfstate` only;
- lock create/get/delete is conditioned to `foundation/default.tflock` only;
- only the applier may create/overwrite `foundation/default.tfstate`;
- the planner may create private reviewed-plan evidence only under `plan-evidence/foundation/`, with unique names and no overwrite/delete permission; and
- the applier may read private reviewed-plan evidence only under that same prefix.

Neither identity receives bootstrap-state content access. Saved plans, raw state, unsanitised plan JSON, generated credentials and real variable files remain private and untracked.

## Keyless GitHub trust

The immutable GitHub subject authorised by the existing provider remains:

```text
repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main
```

The provider preserves `google.subject = assertion.sub` and that exact subject condition. Phase 3 additionally maps GitHub reusable-workflow identity claims:

```text
attribute.job_workflow_ref = assertion.job_workflow_ref
attribute.job_workflow_sha = assertion.job_workflow_sha
```

The existing probe binding remains subject-based and proof-only. Before this mapping is activated in Google Cloud, the federation smoke is migrated to the immutable reusable authentication workflow so the proof path itself carries the reusable-workflow claims.

Planner and applier impersonation are narrower. Each `roles/iam.workloadIdentityUser` binding uses a `principalSet` for exactly one immutable reusable workflow at the Phase 3 control-seed commit:

- planner → `terraform-plan-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`;
- applier → `terraform-apply-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`.

The repository/main subject condition remains an independent provider-level requirement. A candidate branch therefore cannot gain cloud authority merely by naming the service account or copying a workflow. No service-account key may be created.

## Foundation resource authority

The planner and applier use distinct custom roles in the reference project.

Planner permissions are exactly:

- `iam.serviceAccounts.get`;
- `iam.serviceAccountKeys.list`;
- `iam.serviceAccounts.getIamPolicy`; and
- `resourcemanager.projects.getIamPolicy`.

These are used by trusted code to refresh or verify the initial zero-role/zero-key service-account proof. Raw IAM policies or key metadata must not be emitted publicly.

Applier permissions are exactly:

- `iam.serviceAccounts.create`;
- `iam.serviceAccounts.get`; and
- `iam.serviceAccounts.update`.

The authority envelope deliberately excludes service-account deletion, key creation/deletion, `setIamPolicy`, `actAs`, token creation, project IAM mutation and basic/admin roles. If the pinned provider proves an additional permission is genuinely required, stop and amend the governed contract rather than broadening for convenience.

## Cost control

The repository-level architectural constraint remains a normal-spend target of at most **US$5/month** and an engineering ceiling of **US$10/month**.

Cloud Billing budgets, however, use the billing account's native currency. The bootstrap therefore does not hard-code a `currency_code`. The owner supplies `budget_units` as whole units of the billing account's native currency only after current exchange-rate evidence proves that the selected amount is no greater than the US$10 engineering ceiling. A stricter local-currency budget is acceptable; the budget must never be rounded or converted upward beyond the ceiling merely to approximate US$10.

The monthly budget remains scoped to the control and reference project numbers with:

- 50% current-spend threshold;
- 80% current-spend threshold;
- 100% current-spend threshold; and
- 100% forecasted-spend threshold.

For the current owner environment, the billing account is denominated in AUD and the existing bootstrap uses `budget_units = 10`. The evidence establishing that amount remains in the governed issue rather than reusable Terraform.

A budget is a detection control, not a hard cap. Pricing, exchange-rate and free-tier assumptions must be refreshed before any materially cost-bearing execution.

## Phase 3 authority-envelope execution

Landing the Slice C repository candidate does **not** mutate Google Cloud. The bootstrap authority envelope is activated only after the exact candidate receives repository validation, fresh substantive review and merge under issue #14 authority.

Because the existing Phase 2 control plane intentionally has no routine deployment identity permitted to broaden its own authority, Slice C uses one owner-local external bootstrap operation after merge. That operation must:

1. authenticate with short-lived owner credentials and preserve the existing private billing input handling;
2. initialise the existing `bootstrap` GCS backend and use the existing remote state lineage;
3. produce an exact reviewed-main full plan without `-target`;
4. fail unless the plan contains only the approved WIF claim-mapping amendment, planner/applier service accounts, custom roles and bounded IAM/Storage bindings;
5. apply that exact plan without migrating state or changing product runtime;
6. record sanitised resulting-state evidence and a subsequent no-change plan; and
7. immediately rerun the existing federation smoke.

If the post-apply smoke fails, stop Phase 3 and repair the bootstrap control plane before any foundation-state initialisation or planner activation.

## Historical Phase 2 bootstrap evidence

Issue #6 established the projects, private/versioned state bucket, main-only WIF provider, proof identity, billing budget and canonical remote bootstrap state. `docs/gcp-bootstrap-evidence.md` remains the non-sensitive evidence record for that completed bootstrap and must not be rewritten to claim the Phase 3 authority envelope exists before the Slice C cloud operation is actually reconciled.
