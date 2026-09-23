# Phase 5 Slice A — inert product and delivery controls

Governing issue: #109. Approved Gate 1 architecture: issue comments
`5776007863`, `5784177790`, `5784963164`; fresh design review:
`5785093051`. Trusted implementation base:
`0cd67c52995092f946a5408e10e2d6506536d44b`.

## Product boundary

The first accepted product observation comes from the committed final Phase 4
revision release and the Phase 4 terminal record. The schema in
`schemas/phase5/deployment-observed-v1.schema.json` defines one closed
`deployment.observed` v1 event. The pure code in
`services/resilio_app/core.py` fixes identity, RFC 8785 canonicalisation,
evidence ordering, payload hashing and strict rejection. The acceptance fixture
is checked against the committed Phase 4 release, rather than a synthetic
source or a new deployment claim.

One product image can run as three independently permissioned Cloud Run
components: ingestion (one topic publish only), processor (bounded Firestore
read/write only), and read-only API (Firestore read only). The selector chooses
a code path; it is never an IAM boundary. All remain private and scale to zero.

## Inert delivery seed

The Phase 5 build, evidence, deploy, verify, acceptance and Terraform
plan/apply reusable workflows are `workflow_call` only and deliberately have
no caller, OIDC permission, Google authentication, provider access, secrets,
deployment or effective cloud operation. Every workflow calls the closed seed
helper and deliberately **fails closed**; it cannot be promoted as-is into
a live caller. The pure delivery envelope and create-if-absent checks live in
`scripts/phase5_control_seed.py`. The address-only Terraform grammar in
`scripts/phase5_terraform_seed.py` is **not** a live resource attribute
grammar, Terraform root, provider configuration or trusted plan/apply control.

No Phase 4 runtime, workflow, evidence bucket, Artifact Registry or WIF identity
is changed by this slice. A product Terraform state domain is reserved for
`product/default.tfstate` and `product/default.tflock` without creating or
reading either object. Bootstrapping IAM/WIF is **Slice B**, subject to separate
saved-plan review and owner apply authority. Resource creation, product image
build/release, Cloud Run create, post-create IAM D.5 and live acceptance each
retain their separately governed consequence boundaries.

## Exact-candidate checks

The repository's existing credential-free CI must run the additional Phase 5
inert-seed validator and product/negative/idempotency unit tests. In particular,
the tests must establish: closed versioned schema, domain-separated identity
and payload hashes, exact replay without state mutation, permanent rejection
durably recorded before acknowledgement, retryable provider/rejection-record
failure, private API read-only behaviour, no fourth Cloud Run service and no
unexpected Terraform/IAM address. CI success is evidence only, not deployment
or merger authority.

Current product pricing, immutable Firestore database state/location, exact
provider/IAM semantics and real service configuration remain live preflight
requirements before the **first separately authorised cost-bearing plan**.
