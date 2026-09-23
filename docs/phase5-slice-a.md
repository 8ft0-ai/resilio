# Phase 5 Slice A — dormant trusted product controls

Governing issue: #109. Approved Gate 1 architecture: comments
`5776007863`, `5784177790`, `5784963164`; fresh design approval:
`5785093051`. Trusted implementation base:
`0cd67c52995092f946a5408e10e2d6506536d44b`.

## Product boundary

The first product observation is derived from retained final Phase 4 deployment
evidence. The closed v1 schema and `services/resilio_app` implement one
deterministic deployment identity, RFC 8785 canonicalisation for the bounded
schema, exact payload hashing, at-least-once processing, immutable conflict
handling and durable permanent rejection before acknowledgement.

One exact image supports three Cloud Run components with separate runtime
principals: ingest publishes only to the product topic, processor owns the
bounded Firestore state transition, and API is read-only. The component selector
chooses code; IAM remains the authorisation boundary. The Pub/Sub processor
endpoint is the exact service URI root, so its push endpoint and OIDC audience
are identical.

## Dormant trusted delivery controls

Slice A contains the privileged code for product build, evidence, initial
create-only deployment, independent verification, acceptance and product
Terraform plan/apply. These files are reusable `workflow_call` controls only.
There is no protected-main caller, WIF binding, Phase 5 principal, product
Terraform candidate/root, provider credential or cloud activation in Slice A.

The future build is bound to protected main plus the immutable reusable workflow
identity. Evidence binds the exact Cloud Build result, vulnerability result,
pinned Syft SBOM and immutable release envelope. Initial deployment consumes one
owner authority record and has only an exact three-service create-if-absent code
path; it contains no update, delete or IAM-policy mutation path. The separate
verifier/acceptance reusable is designed for the post-D.5 service-level
read/invocation envelope.

The trusted product Terraform implementation lives under
`controls/phase5-product-terraform` and in
`scripts/phase5_terraform_control.py`. A later
`infra/product/candidate.json` is treated only as closed data selecting
`empty`, `base` or `routing`; it cannot supply executable Terraform. The
immutable Slice A helper generates the complete non-IAM resource grammar.
Private state remains reserved to `product/default.tfstate` and normal
`product/default.tflock`; exact plan effects are privately bound and
re-created before apply.

## Authority boundaries

No Phase 4 workflow/runtime/evidence object is modified by Slice A. Slice B is
still required to create the Phase 5 principals, exact WIF bindings and
protected-main callers pinned to the final merged Slice A commit, establish the
product state authority domain, and narrow the Phase 4 verifier before any Phase
5 Cloud Run service exists.

Later product resource creation, image build/evidence, three-service creation,
post-create D.5 IAM, routing subscription and live acceptance retain their
separate plan/review/owner-authority boundaries. The create workflow performs
the all-three-absent provider read after obtaining the future bounded deployer
token because Cloud Run service existence itself requires authenticated provider
read; no mutation occurs before all three absences are established. Fresh
implementation review must assess that sequencing against the accepted Gate 1
design.

## Credential-free validation

Repository CI checks the closed schema/domain vectors, retry/rejection/replay
semantics, owner deployment-authority consumption, exact one-image/three-runtime
release envelope, create-only service request grammar, release-record binding,
closed product Terraform candidate/effect rules, retention of exact Phase 4
blobs and absence of any live `infra/product` root. It also generates the
`empty`, `base` and `routing` product Terraform configurations from the
trusted control and runs Terraform init-without-backend plus validate on each.

CI success is evidence only. It grants no merge, WIF/IAM, Terraform apply,
workflow dispatch, deployment or cloud authority. Pricing/free-tier assumptions,
live Firestore database/location state and live provider/IAM state remain fresh
preflight requirements before the first separately authorised cost-bearing plan.


## Post-review bounded Gate 1 amendment

Issue #109 comment `5793265711` is the governing bounded amendment for the
remediation of PR #110 after the fresh `CHANGES_REQUIRED` review.

The initial create path may mint the already-bounded product-deployer token
before the authenticated all-three-services absence GET preflight. It still may
perform no provider mutation until all three exact service absences have been
proved, and it gains no update, delete or IAM-policy mutation path.

Slice D may use its exact create-operation outcome plus bounded deployer
readback as the create-only result entering D.5. D.5 remains a separately
reviewed and authorised IAM transaction. Independent service/revision/IAM
verification occurs immediately after successful D.5 reconciliation and must
succeed before Slice E. The verifier requires its own immutable reusable WIF
subject; no project-wide Cloud Run read role substitutes for that boundary.

The independent verifier emits a durable routing binding only after successful
attempt-1 verification. A routing Terraform candidate names that evidence
comment and the exact observed `resilio-processor` URI. The trusted planner
and applier revalidate both the comment and its successful protected-main
workflow run before OIDC and bind the evidence into the reviewed private
Terraform effect. A syntactically valid unrelated `*.run.app` URI therefore
cannot establish routing authority.

Product processing stores the first accepted Pub/Sub message ID as immutable
transport metadata outside canonical event identity and payload hashing.
Acceptance first proves the event absent through the API, then binds the ingest
response message ID to the stored first ID; replay must retain the original
stored ID while receiving a distinct transport message ID.

The product image is executed as the `resilio_app.server` module. Repository
CI and the reviewed Cloud Build request start the actual built image in each of
the three component modes, check `/health`, and require an invalid selector to
fail. Product Terraform planner/applier controls also fail before OIDC unless
the caller is `8ft0-ai/resilio`, protected `main`, attempt 1. Future WIF
bindings must preserve the same caller restriction independently.
