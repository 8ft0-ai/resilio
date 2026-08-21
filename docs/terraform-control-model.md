# Terraform control model

## Status

Issue #14 establishes Resilio's Phase 3 Terraform control model. Slice A landed the inert reusable-workflow/control seed at immutable commit `cbfe9821ec07ca6c0c869ebe75100bc500c92a04`. Slice B then migrated the existing manual federation proof to that immutable reusable authentication path and passed the required post-merge smoke from protected `main`.

Slice C declares the bootstrap-owned planner/applier authority envelope in Terraform. **Landing Slice C alone does not activate that authority.** The exact repository candidate must be validated, freshly reviewed and merged before one separately governed owner-local bootstrap plan/apply may change WIF/IAM/Storage authority. The resulting cloud state and immediate regression smoke must then be reconciled before any foundation-state initialisation.

The governing Phase 3 architecture is issue #14 Gate 1 as amended and freshly approved at Gate 2. Its accepted Gate 3 plan deliberately separates immutable trusted workflow code, bootstrap-owned maximum authority, operational state initialisation and later active orchestration.

Issue #28 extends the same authority/evidence pattern for Phase 4 software delivery. Phase 4 Slice A is merged at immutable commit `10e7a938046e2d2d28ffa08a470bf9dfeda40dac`; its tree is the freshly reviewed inert software-supply-chain control seed. Slice A creates no Phase 4 cloud authority merely by existing in Git.

Phase 4 Slice B is the next bounded bootstrap-authority candidate. It re-pins the existing foundation planner/apply/drift trust path to the immutable Slice A seed, declares six future Phase 4 service accounts and narrow custom-role envelopes, and grants only the existing foundation planner/applier the operational read/apply envelopes required for the later Slice C resources. **Slice B does not activate the Phase 4 build/evidence/deploy/verifier identities:** it contains no Phase 4 `workloadIdentityUser` binding, no delivery-identity role grant, no Artifact Registry or evidence-bucket IAM binding, and no runtime project role. A separately reviewed owner-local bootstrap plan/apply is required after Slice B review and merge before any of its declared bootstrap state exists in Google Cloud.

## State and authority domains

`infra/bootstrap` remains the rare control-plane root. It retains the projects, private state bucket, Workload Identity Federation, bootstrap APIs, budget controls and maximum authority envelope for operational identities. Existing bootstrap resources do not move state.

`infra/foundation` is the first normal operational root. Its backend contract is bucket `resilio-control-e882d4-tfstate`, prefix `foundation`, canonical state object `foundation/default.tfstate`, lock object `foundation/default.tflock`, and private reviewed-plan evidence prefix `plan-evidence/foundation/`.

The ordinary root cannot create or broaden the identity that authorises itself. Bootstrap owns distinct `github-foundation-planner` and `github-foundation-applier` identities and their maximum IAM/state authority. The existing `github-federation-probe` remains an authentication proof identity only.

Phase 4 preserves that split. Bootstrap owns the future Phase 4 principals, custom permission envelopes, exact reusable-workflow WIF trust and consequential IAM. Foundation may own only pre-authorised non-IAM operational resources. Slice B gives the foundation identities no custom-role administration, project IAM administration, service-account policy administration, token creation or service-account-key authority.

The six Phase 4 identities declared by Slice B are:

- `github-p4-build@resilio-control-e882d4.iam.gserviceaccount.com` — future trusted build initiator;
- `cloudbuild-p4-builder@resilio-control-e882d4.iam.gserviceaccount.com` — future Cloud Build execution identity;
- `github-p4-evidence@resilio-control-e882d4.iam.gserviceaccount.com` — future evidence adjudicator;
- `github-p4-deployer@resilio-reference-e882d4.iam.gserviceaccount.com` — future exact-digest deployer;
- `p4-proof-runtime@resilio-reference-e882d4.iam.gserviceaccount.com` — future proof-service runtime identity; and
- `github-p4-verifier@resilio-reference-e882d4.iam.gserviceaccount.com` — future independent verifier.

The runtime identity receives zero project roles in Slice B. The five delivery/control identities also receive no delivery-role or GitHub-WIF binding in this slice; those grants are deliberately deferred until the accepted later activation slice after the operational resources exist.

## Candidate boundary

Normal candidate-controlled Terraform is data, not trusted privileged code. The only candidate file remains `infra/foundation/resources.tf.json`.

Before authentication, trusted Python code parses it using duplicate-key rejection. The historical empty and exact `google_service_account.phase3_terraform_sentinel` payloads remain accepted under their closed Phase 3 contract. Phase 4 Slice A additionally defines one exact future foundation document containing the existing sentinel plus the accepted Phase 4 operational APIs, one `us-central1` Artifact Registry repository and one bounded evidence bucket. That document contains no IAM resources, role grants, service-account creation, modules, provider/backend blocks, executable helpers or interpolation. Any extra resource, changed literal, destructive action or unrecognised effect fails closed.

Slice B does **not** replace the current `infra/foundation/resources.tf.json` with the Phase 4 document. The exact future payload remains a reviewed grammar/effect contract for the later separately governed foundation-resource slice.

The privileged working directory is assembled from trusted `backend.tf`, `versions.tf`, `provider.tf` and `.terraform.lock.hcl` checked out from the reusable workflow's own immutable source at `job.workflow_sha`. The exact candidate JSON is fetched by candidate SHA as data and canonicalised before it is copied into that trusted directory. A privileged Terraform workflow never executes an untrusted PR checkout, action, script, provider configuration, backend configuration or module.

## Reusable workflow trust

The Phase 3 control seed contains exactly three original Terraform reusable workflows: `terraform-federation-reusable.yml`, `terraform-plan-reusable.yml` and `terraform-apply-reusable.yml`; the later drift path follows the same immutable-workflow trust model. They remain `workflow_call`-only entry points. Their presence in Git creates **no cloud authority**; cloud capability exists only after a separately governed WIF/IAM binding is activated. Each reusable job checks out security-critical repository code from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}` with persisted checkout credentials disabled.

Phase 4 Slice A adds three separate `workflow_call`-only reusable workflows: `phase4-build-reusable.yml`, `phase4-evidence-reusable.yml` and `phase4-deploy-reusable.yml`. They likewise execute reviewed helper code from their own immutable `job.workflow_sha`, use pinned third-party action identities, expose no ordinary PR/push/manual trigger and consume no long-lived repository secret.

Slice B re-pins the current foundation planner, applier and drift reusable-workflow identities to the immutable Slice A merge seed `10e7a938046e2d2d28ffa08a470bf9dfeda40dac`. The three repository callers are re-pinned to that same seed. This causes future foundation operations, after the separately governed bootstrap authority update, to execute the reviewed Phase 4-aware Terraform control helper while preserving the existing candidate-data boundary.

The historical manual federation smoke deliberately remains on `terraform-federation-reusable.yml@cbfe9821ec07ca6c0c869ebe75100bc500c92a04`, using the unchanged `github-federation-probe` identity. Slice B does not broaden or replace that proof authority.

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

The provider preserves `google.subject = assertion.sub` and mappings for `assertion.job_workflow_ref` and `assertion.job_workflow_sha`. Slice B does not create a duplicate provider or broaden the provider's subject condition.

The existing probe binding remains unchanged in authority. The current planner/applier/drift bindings remain exact reusable-workflow bindings, but Slice B changes their desired immutable workflow identity to the Slice A merge seed:

- `github-foundation-planner` → `terraform-plan-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`;
- `github-foundation-applier` → `terraform-apply-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`; and
- `github-foundation-planner` drift path → `terraform-drift-reusable.yml@10e7a938046e2d2d28ffa08a470bf9dfeda40dac`.

The provider-level repository/main condition still applies independently. Candidate-controlled code therefore cannot mint planner/applier authority merely by naming these identities.

Slice B deliberately contains no WIF binding for `github-p4-build`, `github-p4-evidence`, `github-p4-deployer` or `github-p4-verifier`. Their exact reusable-workflow bindings are deferred to the later Phase 4 activation slice. The builder and runtime identities are provider-execution identities and are not GitHub WIF principals.

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

Slice B adds separate Phase 4 operational envelopes rather than widening those historical roles. The new foundation **reader** envelopes permit only provider readback for Service Usage and, in the control project, the accepted Artifact Registry repository and Cloud Storage bucket resource classes. The new foundation **applier** envelopes add only API enablement plus create/update of the accepted Artifact Registry repository and evidence bucket classes. The reference-project Phase 4 envelope is limited to Service Usage read/enable for the future Cloud Run API.

These envelopes intentionally exclude `setIamPolicy`, service-account administration, custom-role administration, artifact/bucket deletion, object-data authority, service-account impersonation/token creation, Owner/Editor and broad predefined admin roles. If the later exact provider operation cannot complete under the accepted non-IAM envelope, the operation must stop and return to the governed design rather than silently widening foundation authority.

Slice B also declares narrow future role definitions for Cloud Build create/read, builder logging and registry content, evidence read/export, Cloud Run deploy, independent verification and evidence-object create/read. Declaring these custom roles is not a grant: none is bound to a Phase 4 delivery identity in Slice B.

## Foundation state and private evidence authority

Cloud Storage permissions are split so backend discovery does not imply bucket-wide data access.

Both planner and applier receive a list-only custom role with `storage.objects.list` on the state bucket because Terraform 1.15.8's GCS backend enumerates workspaces under its prefix. Read authority uses a separate `storage.objects.get` role conditioned to the exact `foundation/default.tfstate` object.

Normal Terraform backend locking is permitted only for `foundation/default.tflock`, through a custom role containing `storage.objects.create`, `storage.objects.get` and `storage.objects.delete`. This is the minimum operation set required by the pinned GCS backend to create the lock exclusively, inspect it on contention and delete it by matching generation.

Only the applier receives state-write authority for `foundation/default.tfstate`, containing `storage.objects.create` and `storage.objects.delete`. Those permissions are required by Cloud Storage object replacement semantics; the planner never receives them for the state object.

Private reviewed-plan evidence is separate again. The planner receives `storage.objects.create` only, conditioned to `plan-evidence/foundation/`; trusted code uses `ifGenerationMatch=0`, so an existing evidence object cannot be overwritten. The applier receives only `storage.objects.get` on that prefix. Neither identity receives bootstrap-state content access or broad Storage administrative roles.

The planned Phase 4 evidence bucket is a separate operational evidence surface, not a replacement for Terraform state/effect evidence. Slice B declares only future object create/read custom-role envelopes; it does not bind them to the bucket because the bucket does not yet exist. Resource-scoped evidence IAM is deferred to the later activation slice after Slice C creates the bucket.

## Plan evidence and apply interlock

A PR plan is review evidence, not the binary plan later applied. The trusted planner validates an exact open same-repository PR/head/base, accepts only the governed candidate file, records exact configuration/provider/state identities, keeps saved plan/state/`terraform show -json` private and ephemeral, stores a private canonical full-material-effect record in the private state bucket, and emits only a sanitised public manifest containing identity/digests plus resource address/action summaries, policy result and cost classification.

The private representation includes before/after semantics, unknown-value structure, sensitive markers, replacement paths, outputs and other material effect structure. It is never emitted to the public log.

For apply, the trusted workflow proves current protected `main`, the merged PR and reviewed head, fetches both reviewed-head and merged-main `resources.tf.json`, and requires their canonical bytes to match. It then creates a **fresh plan from the merged-main configuration** and current remote state. The current private effect must match the reviewed private effect exactly, including state lineage/serial/object generation and every material plan field. Any mismatch is fail-closed; only the fresh saved plan generated in that same trusted job may be applied.

## Bootstrap activation boundaries

Repository declarations are not cloud evidence. Phase 3 established that bootstrap-owned identity/IAM changes require a separately governed owner-local operation because the normal operational path must not broaden its own authority.

The same rule governs Phase 4 Slice B. After exact candidate CI, a genuinely fresh substantive repository review and merge, one separately governed owner-local bootstrap plan must reconstruct the existing remote `bootstrap` state and show only:

- the three exact foundation reusable-workflow trust re-pins to `10e7a938046e2d2d28ffa08a470bf9dfeda40dac`;
- the six Phase 4 service accounts;
- the accepted custom-role definitions; and
- the four bounded foundation planner/applier Phase 4 project-role bindings.

Any project replacement, state-bucket change, budget change, federation-probe change, Phase 4 WIF activation, delivery-identity role binding, resource-specific Artifact Registry/Storage IAM or unrelated IAM effect invalidates the Slice B plan. The reviewed plan must precede the owner-local apply; apply is without `-target`, followed by a no-change bootstrap plan and regression federation smoke. Slice C cannot begin until that resulting state is reconciled.

## Initial state hand-off

A read-only planner must not create the first state object. A later, separately reviewed temporary main-only setup caller invokes the applier reusable workflow in `initialise-empty-state` mode exactly once. That mode requires `foundation/default.tfstate` to be absent, uses normal backend locking, allows creation only of an empty initial state, and fails if any managed resource is present. Planner activation occurs only after that hand-off succeeds. No `-lock=false` or routine `force-unlock` path is part of the control model.

## Policy, cost and drift

For the initial Phase 3 proof, the strict candidate grammar is also the minimum policy surface: unknown resources and unknown cost classes cannot pass. The sentinel is classified `known-negligible/control-plane`; this does not weaken Resilio's normal US$5/month target or US$10/month engineering ceiling.

Phase 4 keeps the same fail-closed principle. The future exact foundation document is a fixed known resource class rather than an open-ended Terraform surface; supply-chain build/evidence/deploy transitions likewise fail on unrecognised identities, mutable image authority or incomplete evidence. Slice B itself creates only identities/custom-role definitions and foundation authority envelopes when separately applied; it enables no Phase 4 service and therefore has no build, registry, scanning or Cloud Run usage cost. Live Phase 4 pricing evidence is refreshed again before the later slices that actually enable APIs, build or deploy.

Later active Terraform callers use root-scoped non-cancelling, lossless queueing plus backend locking and freshness guards. Weekly/manual drift uses planner authority, never calls `apply`, and produces deduplicated evidence for governed reconciliation rather than silently overwriting unexpected state.

## Security and evidence rules

- no long-lived Google Cloud service-account keys;
- no raw state, saved plan or unsanitised plan JSON in Git or public workflow evidence;
- no bootstrap-state content access for foundation automation;
- no planner state/resource mutation authority beyond the exact ephemeral lock and create-only private evidence object contract;
- no planner ability to impersonate the applier;
- no applier authority to administer project IAM, create service-account keys or delete the protected sentinel;
- no Phase 4 delivery identity is WIF-invokable in Slice B;
- no Phase 4 delivery custom role is granted to a Phase 4 identity in Slice B;
- the Phase 4 runtime identity has zero project roles in Slice B;
- Artifact Registry/evidence-bucket resource IAM is deferred until those resources exist;
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

Phase 4 Slice A added structural checks for the three inert reusable workflows, immutable build/base-image references, absence of unauthorised triggers/secrets, the closed future foundation-resource grammar, supply-chain helper negative paths and the tiny proof-service tests.

Slice B extends bootstrap validation to the exact seven-file bootstrap Terraform configuration, exact six Phase 4 service-account declarations, exact custom-role permission sets, exact four foundation Phase 4 project-role grants, the three foundation caller re-pins, and explicit absence of Phase 4 WIF activation, delivery-role grants, resource IAM, token/`actAs` permission and destructive authority.

No repository validation job performs WIF authentication, live-state planning, Cloud Build execution, Artifact Registry/SBOM writes, Cloud Run deployment or any other cloud mutation.
