# Terraform control model

## Status

Issue #14 establishes Resilio's Phase 3 Terraform control model. Slice A landed the inert reusable-workflow/control seed at immutable commit `cbfe9821ec07ca6c0c869ebe75100bc500c92a04`. Slice B then migrated the existing manual federation proof to that immutable reusable authentication path and passed the required post-merge smoke from protected `main`.

Slice C declares the bootstrap-owned planner/applier authority envelope in Terraform. **Landing Slice C alone does not activate that authority.** The exact repository candidate must be validated, freshly reviewed and merged before one separately governed owner-local bootstrap plan/apply may change WIF/IAM/Storage authority. The resulting cloud state and immediate regression smoke must then be reconciled before any foundation-state initialisation.

The governing Phase 3 architecture is issue #14 Gate 1 as amended and freshly approved at Gate 2. Its accepted Gate 3 plan deliberately separates immutable trusted workflow code, bootstrap-owned maximum authority, operational state initialisation and later active orchestration.

Issue #28 extends the same authority/evidence pattern for Phase 4 software delivery. Its approved Gate 3 Slice A is an **inert control seed only**: it adds trusted reusable build/evidence/deploy workflow code, a tiny proof service and a closed future foundation-resource grammar, but creates no WIF binding, cloud identity, API enablement, build, registry object, SBOM or Cloud Run service merely by landing the repository change.

## State and authority domains

`infra/bootstrap` remains the rare control-plane root. It retains the projects, private state bucket, Workload Identity Federation, bootstrap APIs, budget controls and maximum authority envelope for operational identities. Existing bootstrap resources do not move state.

`infra/foundation` is the first normal operational root. Its backend contract is bucket `resilio-control-e882d4-tfstate`, prefix `foundation`, canonical state object `foundation/default.tfstate`, lock object `foundation/default.tflock`, and private reviewed-plan evidence prefix `plan-evidence/foundation/`.

The ordinary root cannot create or broaden the identity that authorises itself. Bootstrap owns distinct `github-foundation-planner` and `github-foundation-applier` identities and their maximum IAM/state authority. The existing `github-federation-probe` remains an authentication proof identity only.

Phase 4 preserves that split. Bootstrap remains the future owner of the Phase 4 identities, exact reusable-workflow WIF bindings and consequential IAM/custom-role envelopes. Foundation may later own only the bounded operational prerequisites already accepted for Phase 4 after bootstrap separately grants that authority; Slice A itself activates none of it.

## Candidate boundary

Normal candidate-controlled Terraform is data, not trusted privileged code. The only candidate file remains `infra/foundation/resources.tf.json`.

Before authentication, trusted Python code parses it using duplicate-key rejection. The historical empty and exact `google_service_account.phase3_terraform_sentinel` payloads remain accepted under their closed Phase 3 contract. Phase 4 Slice A additionally defines one exact future foundation document containing the existing sentinel plus the accepted Phase 4 operational APIs, one `us-central1` Artifact Registry repository and one bounded evidence bucket. That document contains no IAM resources, role grants, service-account creation, modules, provider/backend blocks, executable helpers or interpolation. Any extra resource, changed literal, destructive action or unrecognised effect fails closed.

Slice A does **not** replace the current `infra/foundation/resources.tf.json` with the Phase 4 document. The exact future payload is only a reviewed grammar/effect contract for the later separately governed foundation-resource slice.

The privileged working directory is assembled from trusted `backend.tf`, `versions.tf`, `provider.tf` and `.terraform.lock.hcl` checked out from the reusable workflow's own immutable source at `job.workflow_sha`. The exact candidate JSON is fetched by candidate SHA as data and canonicalised before it is copied into that trusted directory. A privileged Terraform workflow never executes an untrusted PR checkout, action, script, provider configuration, backend configuration or module.

## Reusable workflow trust

The Phase 3 control seed contains exactly three Terraform reusable workflows: `terraform-federation-reusable.yml`, `terraform-plan-reusable.yml` and `terraform-apply-reusable.yml`; the later drift path follows the same immutable-workflow trust model. They remain `workflow_call`-only entry points. Their presence in Git creates **no cloud authority**; cloud capability exists only after a separately governed WIF/IAM binding is activated. Credential-bearing callers invoke the workflows by an immutable control-seed SHA. Each reusable job checks out security-critical repository code from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}` with persisted checkout credentials disabled.

Phase 4 Slice A adds three separate `workflow_call`-only reusable workflows: `phase4-build-reusable.yml`, `phase4-evidence-reusable.yml` and `phase4-deploy-reusable.yml`. They likewise execute reviewed helper code from their own immutable `job.workflow_sha`, use pinned third-party action identities, expose no ordinary PR/push/manual trigger and consume no long-lived repository secret. Until a later bootstrap slice creates the exact WIF bindings and later caller slices are reviewed and merged, these files are inert code with **no cloud authority**.

Slice B proved the Phase 3 binding operationally: the manual `federation-smoke.yml` on protected `main` called `terraform-federation-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`, used the unchanged `github-federation-probe` service account and obtained the intended 300-second token without resource mutation.

## Phase 4 inert software-supply-chain seed

The Phase 4 trusted helper fixes the initial proof target to control project `resilio-control-e882d4`, reference project `resilio-reference-e882d4`, region `us-central1`, Artifact Registry repository `resilio-phase4`, image `phase4-proof`, evidence bucket `resilio-control-e882d4-phase4-evidence` and Cloud Run service `phase4-proof`.

The build contract is source- and control-bound. It accepts an exact 40-character source SHA and the immutable reusable-workflow SHA, constructs the Cloud Build request internally, fixes the dedicated builder identity, requires generated provenance, declares the output through the build `images` field and permits no caller-controlled decision-critical substitutions. Build steps and the proof-service base image are referenced by immutable digest; the proof Dockerfile performs no package installation or mutable network dependency resolution and runs as non-root.

The evidence contract is deliberately separate from build and deployment authority. It validates the exact successful build/source/resulting digest, requires completed vulnerability analysis, treats CRITICAL findings as failure and HIGH findings as a separate reviewed disposition, requires an exact-digest native SBOM reference, and constructs a compact transition manifest only when the accepted evidence set is complete. Evidence retry is not rebuild authority.

The deployment contract accepts only a previously adjudicated PASS transition manifest. It derives the exact `@sha256:` image itself, fixes the reference project/region/service/runtime identity and scale bounds, and never builds or pushes an image. Independent readback rejects public principals, verifies the service/revision image digest and runtime posture, and treats the application health response as supplemental evidence rather than proof of the serving digest.

The proof service itself is deliberately trivial Python standard-library HTTP code with no application dependency or secret. `/healthz` exposes only non-sensitive health/source metadata supplied through the deployment contract. This remains Phase 4 proof infrastructure and does not introduce Phase 5 product semantics.

## Workload Identity Federation authority

The shared GitHub WIF provider continues to require the immutable Resilio `refs/heads/main` subject:

```text
repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main
```

Slice C desired state preserves `google.subject = assertion.sub` and adds mappings for `assertion.job_workflow_ref` and `assertion.job_workflow_sha`. It does not create a duplicate provider or broaden the provider's subject condition.

The existing probe binding remains unchanged in authority. Planner/applier bindings are narrower: each service account may be impersonated only through a `principalSet` whose `attribute.job_workflow_ref` equals its corresponding reusable workflow at the immutable Phase 3 control-seed SHA:

- `github-foundation-planner` → `terraform-plan-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`;
- `github-foundation-applier` → `terraform-apply-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`.

The provider-level repository/main condition still applies independently. Candidate-controlled code therefore cannot mint planner/applier authority merely by naming these identities.

Phase 4 Slice A does not add build/evidence/deployer/verifier WIF bindings. Those are explicitly deferred to the later bootstrap authority slice after this inert seed has been freshly reviewed and merged to an immutable control-seed SHA.

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

The planned Phase 4 evidence bucket is a separate operational evidence surface, not a replacement for Terraform state/effect evidence. Slice A only fixes its future literal resource shape (uniform bucket-level access, public-access prevention, versioning, bounded lifecycle, `force_destroy = false` and deletion prevention); it grants no object permissions.

## Plan evidence and apply interlock

A PR plan is review evidence, not the binary plan later applied. The trusted planner validates an exact open same-repository PR/head/base, accepts only the governed candidate file, records exact configuration/provider/state identities, keeps saved plan/state/`terraform show -json` private and ephemeral, stores a private canonical full-material-effect record in the private state bucket, and emits only a sanitised public manifest containing identity/digests plus resource address/action summaries, policy result and cost classification.

The private representation includes before/after semantics, unknown-value structure, sensitive markers, replacement paths, outputs and other material effect structure. It is never emitted to the public log.

For apply, the trusted workflow proves current protected `main`, the merged PR and reviewed head, fetches both reviewed-head and merged-main `resources.tf.json`, and requires their canonical bytes to match. It then creates a **fresh plan from the merged-main configuration** and current remote state. The current private effect must match the reviewed private effect exactly, including state lineage/serial/object generation and every material plan field. Any mismatch is fail-closed; only the fresh saved plan generated in that same trusted job may be applied.

## Slice C activation boundary

The repository declaration of planner/applier identities and IAM grants is not itself cloud evidence. After Slice C receives exact-candidate validation, fresh review and merge, one owner-local bootstrap operation activates the envelope because the Phase 2 control plane deliberately lacks an automation identity allowed to broaden its own authority.

That operation must use the existing remote `bootstrap` state, produce a full reviewed-main plan, reject any effect outside the expected WIF claim mapping/service accounts/custom roles/bindings, apply without `-target`, record sanitised resulting-state evidence and prove a subsequent no-change plan. The existing federation smoke is then rerun immediately. A smoke regression stops the Phase 3 sequence before foundation state is created.

The same non-self-expansion rule governs Phase 4. Future software-delivery identities and WIF/IAM grants are bootstrap-owned and require their separately reviewed owner-local bootstrap plan/apply boundary; the ordinary foundation root cannot grant them to itself.

## Initial state hand-off

A read-only planner must not create the first state object. A later, separately reviewed temporary main-only setup caller invokes the applier reusable workflow in `initialise-empty-state` mode exactly once. That mode requires `foundation/default.tfstate` to be absent, uses normal backend locking, allows creation only of an empty initial state, and fails if any managed resource is present. Planner activation occurs only after that hand-off succeeds. No `-lock=false` or routine `force-unlock` path is part of the control model.

## Policy, cost and drift

For the initial Phase 3 proof, the strict candidate grammar is also the minimum policy surface: unknown resources and unknown cost classes cannot pass. The sentinel is classified `known-negligible/control-plane`; this does not weaken Resilio's normal US$5/month target or US$10/month engineering ceiling.

Phase 4 keeps the same fail-closed principle. The future exact foundation document is a fixed known resource class rather than an open-ended Terraform surface; supply-chain build/evidence/deploy transitions likewise fail on unrecognised identities, mutable image authority or incomplete evidence. Live Phase 4 cost/pricing evidence is refreshed again before the later slices that actually enable APIs, build or deploy.

Later active Terraform callers use root-scoped non-cancelling, lossless queueing plus backend locking and freshness guards. Weekly/manual drift uses planner authority, never calls `apply`, and produces deduplicated evidence for governed reconciliation rather than silently overwriting unexpected state.

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
- Phase 4 build/evidence/deploy capabilities remain distinct and exact-digest bound;
- mutable tags are never deployment authority;
- missing/malformed provenance, vulnerability or SBOM evidence is not a PASS;
- public unauthenticated Cloud Run principals are forbidden by the proof contract;
- partial apply, build, deployment or verification failure is evidence for governed recovery, not authority for automatic permission widening or substitution.

## Repository validation

Repository validation remains credential-free. It verifies the closed foundation contract, immutable action/workflow pins, strict candidate grammar, canonical effect logic, secret/state filename exclusions, exact bootstrap/WIF authority-envelope constraints, forbidden broad roles/permissions and Terraform formatting/init-without-backend/validation for both roots.

Phase 4 Slice A extends that credential-free validation with structural checks for the three inert reusable workflows, immutable build/base-image references, absence of unauthorised triggers/secrets, the closed future foundation-resource grammar, supply-chain helper negative paths and the tiny proof-service tests.

No repository validation job performs WIF authentication, live-state planning, Cloud Build execution, Artifact Registry/SBOM writes, Cloud Run deployment or any other cloud mutation.
