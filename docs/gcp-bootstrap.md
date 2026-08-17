# GCP bootstrap control boundary

Issue #6 establishes the first Google Cloud control-plane slice for Resilio. This document defines the repository-side bootstrap contract; it is not evidence that any cloud resource already exists.

## Intended final state

The canonical reference deployment uses two projects:

- a **control project** for Terraform state, Workload Identity Federation and the narrowly scoped bootstrap identity; and
- a **reference project** that establishes the future workload-plane boundary but contains no product/runtime resources in this slice.

The project IDs are non-secret owner-supplied execution inputs. The billing-account ID and any real local variable values remain owner-local and must not be committed.

The first Terraform root is [`../infra/bootstrap`](../infra/bootstrap). It is intentionally limited to project/control resources needed to prove private state, keyless GitHub identity and cost detection.

## Tooling and validation

Terraform is pinned by `.terraform-version` to `1.15.8`. The root constrains `hashicorp/google` to `~> 7.42.0`, and `infra/bootstrap/.terraform.lock.hcl` records the provider selected and integrity hashes produced by Terraform itself.

The required `repository` GitHub check remains credential-free. It:

1. runs repository invariant validation;
2. checks Terraform formatting;
3. runs `terraform init -backend=false -lockfile=readonly`; and
4. runs `terraform validate`.

The pull-request workflow has only `contents: read`. It does not request `id-token: write`, consume GCP credentials or execute `terraform plan` against live cloud state.

## Project creation modes

Google Cloud project creation has an unavoidable environment-dependent bootstrap boundary. The approved issue #6 amendment therefore defines two explicit modes.

### Existing organisation or folder

Use `project_creation_mode = "managed-parent"` with an existing authorised `organization` or `folder` parent.

Before any mutation, read the effective `constraints/compute.skipDefaultNetworkCreation` policy. Do not create or broaden an organisation policy in this slice.

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

The root declares only:

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
- one federation-probe service account and its impersonation binding; and
- one monthly billing budget covering the two projects.

Cloud Run, Pub/Sub, Firestore, BigQuery, Cloud Build, Artifact Registry, GKE and other product/runtime services are outside this slice.

## Terraform state

The state bucket is regional Standard storage in `US-CENTRAL1` and must have:

- public access prevention enforced;
- uniform bucket-level access;
- object versioning;
- `force_destroy = false`;
- Terraform `prevent_destroy`; and
- Google-managed encryption for this bootstrap.

The normal bucket name is `<control-project-id>-tfstate`. If that globally unique name is unavailable, stop and record an explicitly approved non-secret suffix rather than silently generating a canonical name.

Gate A deliberately has no `backend "gcs"` block. Gate B starts with temporary local bootstrap state, creates and verifies the bucket, then migrates that exact state to GCS. Gate C records the canonical non-sensitive backend identifiers after the cloud resources exist.

Any local `.tfstate`, backups, plans, generated credentials and real variable files are ignored and must be removed after migration. Terraform state is sensitive operational data even when the repository is public.

## Keyless GitHub trust

The current immutable GitHub subject authorised by this bootstrap is:

```text
repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main
```

The Workload Identity Provider maps only `google.subject = assertion.sub` and its attribute condition requires that exact subject.

The resulting federated principal may impersonate only the dedicated `github-federation-probe` service account through `roles/iam.workloadIdentityUser`. The probe service account receives no project resource role in this slice.

A successful short-lived token exchange from trusted `main` is sufficient proof. No service-account key may be created. Public pull requests receive no cloud identity.

## Cost control

The repository-level architectural constraint remains a normal-spend target of at most **US$5/month** and an engineering ceiling of **US$10/month**.

Cloud Billing budgets, however, use the billing account's native currency. The bootstrap therefore does not hard-code a `currency_code`. Gate B supplies `budget_units` as whole units of the billing account's native currency only after current exchange-rate evidence proves that the selected amount is no greater than the US$10 engineering ceiling. A stricter local-currency budget is acceptable; the budget must never be rounded or converted upward beyond the ceiling merely to approximate US$10.

The monthly budget remains scoped to the control and reference project numbers with:

- 50% current-spend threshold — at or below the US$5 normal target when the selected budget is at or below the US$10 ceiling;
- 80% current-spend threshold — early warning;
- 100% current-spend threshold — the selected conservative alert boundary; and
- 100% forecasted-spend threshold.

For the current issue #6 owner environment, the billing account is denominated in AUD and Gate B uses `budget_units = 10`. The evidence establishing that AUD 10 is below the US$10 ceiling is recorded in the governed issue rather than hard-coded into reusable Terraform.

Default billing-recipient notifications are used; no Pub/Sub or automated billing shutdown is introduced.

A budget is a detection control, not a hard cap. Pricing, exchange-rate and free-tier assumptions must be refreshed immediately before Gate B execution.

## Gate B execution and evidence

Cloud mutation requires the still-valid issue #6 authority and owner-authenticated short-lived credentials. Before applying:

1. refresh `main`, the governing comments and current official pricing/capability facts;
2. verify project-ID availability, hierarchy, effective default-network policy, billing access and permissions;
3. read the billing account's native currency and choose `budget_units` only after proving the resulting local-currency amount is no greater than the current US$10 engineering ceiling;
4. select exactly one project creation mode;
5. initialise with a temporary local backend;
6. if Terraform must create projects under a parent, establish those project prerequisites first, then produce the authoritative full plan for the remaining bootstrap;
7. if projects were precreated, import both before producing the authoritative full plan;
8. inspect the plan and stop on any resource, IAM grant, service or cost-control shape outside the approved boundary.

After apply, independently re-read the projects, enabled services, bucket controls, Workload Identity configuration, service-account keys/IAM and budget. Then migrate the same state to GCS and prove both remote-state readability and local-state removal.

Any unexpected existing project, hierarchy, IAM, resource, network, pricing, state-migration or authentication condition is fail-closed. Do not compensate with Owner/Editor roles, service-account keys, public state, repository bypasses or broader APIs.

## Gate C

After successful owner-local bootstrap, a separate reconciliation PR records only non-sensitive canonical identifiers and evidence, adds the manual trusted-`main` federation smoke workflow, and undergoes a genuinely fresh substantive review before merge.

Gate A repository code does not itself mutate Google Cloud.
