# Terraform control model

## Status

Issue #14 establishes Resilio's Phase 3 Terraform control model. Slice A landed the inert reusable-workflow/control seed at immutable commit `cbfe9821ec07ca6c0c869ebe75100bc500c92a04`. Slice B then migrated the existing manual federation proof to that immutable reusable authentication path and passed the required post-merge smoke from protected `main`.

Slice C declares the bootstrap-owned planner/applier authority envelope in Terraform. **Landing Slice C alone does not activate that authority.** The exact repository candidate must be validated, freshly reviewed and merged before one separately governed owner-local bootstrap plan/apply may change WIF/IAM/Storage authority. The resulting cloud state and immediate regression smoke must then be reconciled before any foundation-state initialisation.

The governing Phase 3 architecture is issue #14 Gate 1 as amended and freshly approved at Gate 2. Its accepted Gate 3 plan deliberately separates immutable trusted workflow code, bootstrap-owned maximum authority, operational state initialisation and later active orchestration.

Issue #28 extends the same authority/evidence pattern for Phase 4 software delivery. Phase 4 Slice A is merged at immutable commit `10e7a938046e2d2d28ffa08a470bf9dfeda40dac`; its tree is the freshly reviewed inert software-supply-chain control seed. Slice A creates no Phase 4 cloud authority merely by existing in Git.

Phase 4 Slice B is merged and reconciled. It re-pinned the existing foundation planner/apply/drift trust path to the immutable Slice A seed, created six Phase 4 service accounts and narrow custom-role envelopes, and granted only the existing foundation planner/applier the operational read/apply envelopes required for Slice C. Slice B deliberately did not activate Phase 4 delivery WIF or delivery-role grants.

Phase 4 Slice C is also complete. Protected `main` at `b680cd045b336da05c7d36aefae151b624f69995` contains the reviewed operational foundation configuration; the trusted protected-main apply created only the accepted Phase 4 APIs, Artifact Registry repository `resilio-phase4` and evidence bucket `resilio-control-e882d4-phase4-evidence`, then an immediate trusted plan proved no change.

Phase 4 Slice D is the bounded authority-activation change. Its Git candidate adds only the accepted delivery-role bindings, exact reusable-workflow WIF bindings and resource-scoped Artifact Registry/evidence-bucket access required by the already-reviewed Slice A workflows. **A merged Slice D declaration is still not cloud evidence or authority by itself.** Before live activation, the exact candidate and one owner-local bootstrap plan require fresh substantive review; only the reviewed plan may then be applied, followed by a full no-change plan and regression federation/foundation checks. Slice E must not begin until that resulting state is reconciled.

## State and authority domains

`infra/bootstrap` remains the rare control-plane root. It retains the projects, private state bucket, Workload Identity Federation, bootstrap APIs, budget controls and maximum authority envelope for operational identities. Existing bootstrap resources do not move state.

`infra/foundation` is the first normal operational root. Its backend contract is bucket `resilio-control-e882d4-tfstate`, prefix `foundation`, canonical state object `foundation/default.tfstate`, lock object `foundation/default.tflock`, and private reviewed-plan evidence prefix `plan-evidence/foundation/`.

The ordinary root cannot create or broaden the identity that authorises itself. Bootstrap owns distinct `github-foundation-planner` and `github-foundation-applier` identities and their maximum IAM/state authority. The existing `github-federation-probe` remains an authentication proof identity only.

Phase 4 preserves that split. Bootstrap owns the Phase 4 principals, custom permission envelopes, exact reusable-workflow WIF trust and consequential IAM. Foundation owns only pre-authorised non-IAM operational resources. The foundation identities have no custom-role administration, project IAM administration, service-account policy administration, token creation or service-account-key authority.

The six Phase 4 identities are:

- `github-p4-build@resilio-control-e882d4.iam.gserviceaccount.com` — trusted build initiator;
- `cloudbuild-p4-builder@resilio-control-e882d4.iam.gserviceaccount.com` — Cloud Build execution identity;
- `github-p4-evidence@resilio-control-e882d4.iam.gserviceaccount.com` — evidence adjudicator;
- `github-p4-deployer@resilio-reference-e882d4.iam.gserviceaccount.com` — exact-digest deployer;
- `p4-proof-runtime@resilio-reference-e882d4.iam.gserviceaccount.com` — proof-service runtime identity; and
- `github-p4-verifier@resilio-reference-e882d4.iam.gserviceaccount.com` — independent verifier.

The runtime identity receives zero project roles. Slice D grants the other identities only their accepted consequence-bounded roles; it does not turn the builder or runtime identity into GitHub WIF principals.

## Candidate boundary

Normal candidate-controlled Terraform is data, not trusted privileged code. The only candidate file for the normal foundation path remains `infra/foundation/resources.tf.json`.

Before authentication, trusted Python code parses it using duplicate-key rejection. The historical empty and exact `google_service_account.phase3_terraform_sentinel` payloads remain accepted under their closed Phase 3 contract. Phase 4 additionally defines one exact foundation document containing the existing sentinel plus the accepted Phase 4 operational APIs, one `us-central1` Artifact Registry repository and one bounded evidence bucket. That document contains no IAM resources, role grants, service-account creation, modules, provider/backend blocks, executable helpers or interpolation. Any extra resource, changed literal, destructive action or unrecognised effect fails closed.

Slice C placed that exact Phase 4 document on protected `main` and the trusted plan/apply path reconciled it to no change. The operational foundation state therefore owns the accepted non-IAM resources, but still cannot grant the delivery authority defined in bootstrap.

The privileged working directory is assembled from trusted `backend.tf`, `versions.tf`, `provider.tf` and `.terraform.lock.hcl` checked out from the reusable workflow's own immutable source at `job.workflow_sha`. The exact candidate JSON is fetched by candidate SHA as data and canonicalised before it is copied into that trusted directory. A privileged Terraform workflow never executes an untrusted PR checkout, action, script, provider configuration, backend configuration or module.

## Reusable workflow trust

The Phase 3 control seed contains exactly three original Terraform reusable workflows: `terraform-federation-reusable.yml`, `terraform-plan-reusable.yml` and `terraform-apply-reusable.yml`; the later drift path follows the same immutable-workflow trust model. They remain `workflow_call`-only entry points. Their presence in Git creates **no cloud authority**; cloud capability exists only after a separately governed WIF/IAM binding is activated. Each reusable job checks out security-critical repository code from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}` with persisted checkout credentials disabled.

Phase 4 Slice A adds three separate `workflow_call`-only reusable workflows: `phase4-build-reusable.yml`, `phase4-evidence-reusable.yml` and `phase4-deploy-reusable.yml`. They likewise execute reviewed helper code from their own immutable `job.workflow_sha`, use pinned third-party action identities, expose no ordinary PR/push/manual trigger and consume no long-lived repository secret.

The current foundation planner, applier and drift reusable-workflow identities are pinned to the immutable Slice A merge seed `10e7a938046e2d2d28ffa08a470bf9dfeda40dac`. The three repository callers are pinned to that same seed. This lets normal foundation operations execute the reviewed Phase 4-aware Terraform control helper while preserving the existing candidate-data boundary.

The historical manual federation smoke deliberately remains on `terraform-federation-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`, using the unchanged `github-federation-probe` identity. Phase 4 does not broaden or replace that proof authority.

## Phase 4 trusted software-supply-chain seed

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

The provider preserves `google.subject = assertion.sub` and mappings for `assertion.job_workflow_ref` and `assertion.job_workflow_sha`. Slice D does not create a duplicate provider or broaden the provider's subject condition.

The existing probe binding remains unchanged in authority. The planner/applier/drift bindings remain exact reusable-workflow bindings at the Slice A merge seed:

- `github-foundation-planner` → `terraform-plan-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`;
- `github-foundation-applier` → `terraform-apply-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`; and
- `github-foundation-planner` drift path → `terraform-drift-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`.

Slice D declares exactly four additional GitHub WIF bindings, each still subject to the provider-level protected-main condition:

- `github-p4-build` → `phase4-build-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`;
- `github-p4-evidence` → `phase4-evidence-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`;
- `github-p4-deployer` → `phase4-deploy-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`; and
- `github-p4-verifier` → that same immutable deploy reusable workflow, where verification is a separate job and identity.

The builder and runtime identities are provider-execution identities and are not GitHub WIF principals. A caller cannot gain delivery authority by merely naming one of the service accounts; the WIF `principalSet` also requires the exact immutable `job_workflow_ref`.

## Phase 4 delivery authority

Slice B declared the narrow custom roles; Slice D binds them without broadening their permission sets.

The build initiator receives only `cloudbuild.builds.create/get/list` at control-project scope and `roles/iam.serviceAccountUser` **on the dedicated builder service account only**. It receives no Artifact Registry write, Run, foundation, project-IAM or service-account administration authority.

The builder receives its custom Cloud Logging writer role at control-project scope and the custom registry-content role **on repository `resilio-phase4` only**. It can upload/read the fixed proof image content and tags but cannot administer/delete the repository or deploy Cloud Run.

The evidence adjudicator receives only `cloudbuild.builds.get` plus `containeranalysis.occurrences.list` at control-project scope, Artifact Registry Reader on `resilio-phase4`, and custom object create/read roles limited by IAM condition to `transitions/` objects in `resilio-control-e882d4-phase4-evidence`. The immutable v1 `ExportSBOM` path currently uses occurrence-list authority; Slice D does not pre-grant broad storage access to provider-selected native-SBOM storage. Slice E is the explicit feasibility proof: if native SBOM export/readback cannot succeed within the accepted bounded envelope, the workflow must stop and return to architecture rather than gaining project-wide Storage Admin/Object Admin.

The deployer receives only the custom Cloud Run create/update/get/operation-read role in the single-service reference project, Artifact Registry Reader on the exact control-project repository, transition-object read on the exact evidence prefix, and `roles/iam.serviceAccountUser` **on `p4-proof-runtime` only**. It receives no Run IAM-policy mutation or image write authority.

The runtime service account receives zero project roles and no user-managed key.

The verifier receives only the custom service/revision/IAM readback and `run.routes.invoke` role in the Phase 4 single-service reference project. It receives no create/update/delete/set-IAM authority. This bounded project scope is accepted only while the reference project contains the single Phase 4 proof service; service-scoped narrowing is mandatory before a later phase introduces another service.

The Google-managed Cloud Run service agent for reference project number `144158187163` receives Artifact Registry Reader on `resilio-phase4` only so Cloud Run can consume the cross-project image. It receives no broader control-project repository role from this slice.

No project-wide `roles/storage.admin`, `roles/storage.objectAdmin`, `roles/artifactregistry.writer`, `roles/run.admin`, Owner or Editor role is part of this model.

## Planner and applier resource authority

The historical planner reference-project custom role remains limited to:

- `iam.serviceAccounts.get`;
- `iam.serviceAccountKeys.list`;
- `iam.serviceAccounts.getIamPolicy`; and
- `resourcemanager.projects.getIamPolicy`.

The historical applier reference-project custom role remains limited to:

- `iam.serviceAccounts.create`;
- `iam.serviceAccounts.get`; and
- `iam.serviceAccounts.update`.

Phase 4 adds separate operational envelopes rather than widening those historical roles. The foundation **reader** envelopes permit only provider readback for Service Usage and, in the control project, the accepted Artifact Registry repository and Cloud Storage bucket resource classes. The foundation **applier** envelopes add only API enablement plus create/update of the accepted Artifact Registry repository and evidence bucket classes. The reference-project Phase 4 envelope is limited to Service Usage read/enable for Cloud Run.

These envelopes intentionally exclude `setIamPolicy`, service-account administration, custom-role administration, artifact/bucket deletion, object-data authority, service-account impersonation/token creation, Owner/Editor and broad predefined admin roles. If an exact provider operation cannot complete under the accepted non-IAM envelope, the operation must stop and return to the governed design rather than silently widening foundation authority.

## Foundation state and private evidence authority

Cloud Storage permissions are split so backend discovery does not imply bucket-wide data access.

Both planner and applier receive a list-only custom role with `storage.objects.list` on the state bucket because Terraform 1.15.8's GCS backend enumerates workspaces under its prefix. Read authority uses a separate `storage.objects.get` role conditioned to the exact `foundation/default.tfstate` object.

Normal Terraform backend locking is permitted only for `foundation/default.tflock`, through a custom role containing `storage.objects.create`, `storage.objects.get` and `storage.objects.delete`. This is the minimum operation set required by the pinned GCS backend to create the lock exclusively, inspect it on contention and delete it by matching generation.

Only the applier receives state-write authority for `foundation/default.tfstate`, containing `storage.objects.create` and `storage.objects.delete`. Those permissions are required by Cloud Storage object replacement semantics; the planner never receives them for the state object.

Private reviewed-plan evidence is separate again. The planner receives `storage.objects.create` only, conditioned to `plan-evidence/foundation/`; trusted code uses `ifGenerationMatch=0`, so an existing evidence object cannot be overwritten. The applier receives only `storage.objects.get` on that prefix. Neither identity receives bootstrap-state content access or broad Storage administrative roles.

The Phase 4 evidence bucket is a separate operational evidence surface, not a replacement for Terraform state/effect evidence. Slice D binds evidence create/read and deployer read only to the exact `transitions/` object prefix. The native provider-generated SBOM object is not silently folded into this authority; its actual storage/read requirements remain a bounded Slice E feasibility checkpoint.

## Plan evidence and apply interlock

A PR plan is review evidence, not the binary plan later applied. The trusted planner validates an exact open same-repository PR/head/base, accepts only the governed candidate file, records exact configuration/provider/state identities, keeps saved plan/state/`terraform show -json` private and ephemeral, stores a private canonical full-material-effect record in the private state bucket, and emits only a sanitised public manifest containing identity/digests plus resource address/action summaries, policy result and cost classification.

The private representation includes before/after semantics, unknown-value structure, sensitive markers, replacement paths, outputs and other material effect structure. It is never emitted to the public log.

For apply, the trusted workflow proves current protected `main`, the merged PR and reviewed head, fetches both reviewed-head and merged-main `resources.tf.json`, and requires their canonical bytes to match. It then creates a **fresh plan from the merged-main configuration** and current remote state. The current private effect must match the reviewed private effect exactly, including state lineage/serial/object generation and every material plan field. Any mismatch is fail-closed; only the fresh saved plan generated in that same trusted job may be applied.

## Bootstrap activation boundaries

Repository declarations are not cloud evidence. Bootstrap-owned identity/IAM changes require a separately governed owner-local operation because the normal operational path must not broaden its own authority.

For Slice D, after exact candidate CI and merge sequencing required by the governing review handoff, one owner-local bootstrap plan must reconstruct the existing remote `bootstrap` state and show only the accepted authority transition:

- no changes to the two projects, billing budget, state bucket, WIF pool/provider condition, federation probe, foundation state/effect authority or existing service-account identities;
- the existing narrow custom-role definitions remain permission-identical;
- five delivery/control identities receive only their accepted project-scoped custom roles while the runtime identity receives zero project role;
- exactly four Phase 4 WIF `workloadIdentityUser` bindings to the immutable Slice A reusable workflows;
- `roles/iam.serviceAccountUser` only from build initiator to builder and from deployer to runtime;
- exactly four Artifact Registry repository-local bindings: builder content role, evidence reader, deployer reader and the reference-project Cloud Run service-agent reader;
- exactly three evidence-bucket bindings, all conditionally restricted to `transitions/`: evidence create/read and deployer read; and
- non-sensitive outputs for the exact workflow refs and principal identities.

Any project replacement, state/budget change, WIF provider broadening, runtime project role, broad storage/registry/run role, unexpected principal, additional service-account impersonation, unrelated IAM effect or destructive effect invalidates the Slice D plan. The reviewed plan must precede the owner-local apply; apply is without `-target`, followed by a full no-change bootstrap plan and regression federation/foundation checks. No Cloud Build execution is part of Slice D because the manual caller workflows are introduced only in Slice E.

## Initial state hand-off

A read-only planner must not create the first state object. The Phase 3 one-time setup path invoked the applier reusable workflow in `initialise-empty-state` mode exactly once. That mode required `foundation/default.tfstate` to be absent, used normal backend locking, allowed creation only of an empty initial state, and failed if any managed resource was present. No `-lock=false` or routine `force-unlock` path is part of the control model.

## Policy, cost and drift

For the initial Phase 3 proof, the strict candidate grammar is also the minimum policy surface: unknown resources and unknown cost classes cannot pass. The sentinel is classified `known-negligible/control-plane`; this does not weaken Resilio's normal US$5/month target or US$10/month engineering ceiling.

Phase 4 keeps the same fail-closed principle. The exact foundation document is a fixed known resource class rather than an open-ended Terraform surface; supply-chain build/evidence/deploy transitions likewise fail on unrecognised identities, mutable image authority or incomplete evidence. Slice C enabled the required APIs and created empty bounded repository/evidence resources; Slice D changes IAM only and performs no build, image push, scan, SBOM export or Cloud Run revision. The first predictable per-digest scan cost therefore begins only with the separately governed Slice E build/evidence proof and remains subject to the Phase 4 unique-digest budget.

Active Terraform callers use root-scoped non-cancelling, lossless queueing plus backend locking and freshness guards. Weekly/manual drift uses planner authority, never calls `apply`, and produces deduplicated evidence for governed reconciliation rather than silently overwriting unexpected state.

## Security and evidence rules

- no long-lived Google Cloud service-account keys;
- no raw state, saved plan or unsanitised plan JSON in Git or public workflow evidence;
- no bootstrap-state content access for foundation automation;
- no planner state/resource mutation authority beyond the exact ephemeral lock and create-only private evidence object contract;
- no planner ability to impersonate the applier;
- no applier authority to administer project IAM, create service-account keys or delete the protected sentinel;
- Phase 4 GitHub federation is tied to the protected-main subject plus exact immutable reusable-workflow identities;
- build initiator can `actAs` only the dedicated builder; deployer can `actAs` only the zero-project-role runtime identity;
- builder registry authority and Cloud Run service-agent read authority are repository-scoped to `resilio-phase4`;
- evidence transition create/read and deployer evidence read are bucket- and `transitions/`-prefix-scoped;
- no broad storage administration is pre-granted for native SBOM export; inability to prove that path is a hard architecture return, not permission-widening authority;
- generated WIF credential material is ephemeral;
- private Terraform effect evidence is write-once by exact PR/head object identity;
- stale PR, current-main, configuration, state or effect identity stops before apply;
- Phase 4 build/evidence/deploy capabilities remain distinct and exact-digest bound;
- mutable tags are never deployment authority;
- missing/malformed provenance, vulnerability or SBOM evidence is not a PASS;
- public unauthenticated Cloud Run principals are forbidden by the proof contract;
- partial apply, build, deployment or verification failure is evidence for governed recovery, not authority for automatic permission widening or substitution.

## Repository validation

Repository validation remains credential-free. It verifies the closed foundation contract, immutable action/workflow pins, strict candidate grammar, canonical effect logic, secret/state filename exclusions, exact bootstrap/WIF authority-envelope constraints, forbidden broad roles/permissions and Terraform formatting/init-without-backend/validation for both roots.

Phase 4 Slice A added structural checks for the three inert reusable workflows, immutable build/base-image references, absence of unauthorised triggers/secrets, the closed foundation-resource grammar, supply-chain helper negative paths and the tiny proof-service tests.

Slice B extended bootstrap validation to the exact seven-file bootstrap Terraform configuration, exact six Phase 4 service-account declarations, exact custom-role permission sets, exact four foundation Phase 4 project-role grants and the three foundation caller re-pins while explicitly forbidding delivery activation.

Slice D advances that closed bootstrap grammar rather than opening it. Validation pins the exact modified Terraform blobs and requires exactly nine Phase 4 project IAM bindings, four immutable-workflow WIF bindings, two narrowly scoped service-account-user bindings, four repository-local Artifact Registry bindings and three transition-prefix evidence-bucket bindings. It also proves the runtime has no project role and rejects broad predefined roles, destructive permissions, token/key administration and any unrecognised authority expansion.

No repository validation job performs WIF authentication, live-state planning, Cloud Build execution, Artifact Registry/SBOM writes, Cloud Run deployment or any other cloud mutation.
