# Phase 5 Slice B — authority/state-domain activation declaration

Governing issue: #109. Effective Gate 1 design: comments `5776007863`,
`5784177790`, `5784963164`; bounded post-implementation amendment
`5793265711`; provider-semantic IAM architecture amendment `5825076422`,
freshly approved by review `5825092955` and accepted by owner authority
`5825134357`. Slice A control identity:
`67e61a6c0d4930f8a5c5db545ef84d8430e437bc`.

## Outcome

Slice B declares the repository side of the Phase 5 authority and product-state
domains without activating them in Google Cloud.

The live product root is now `infra/product/candidate.json`, using the exact
closed grammar implemented by the immutable Slice A trusted Terraform control.
Its initial stage is `empty`, so assembling the product Terraform document
produces no product resources. Product state remains reserved to
`product/default.tfstate`, its lock to `product/default.tflock`, and reviewed
plan evidence to `plan-evidence/product/`.

Bootstrap declares dedicated Phase 5 identities for build initiation, build
execution, evidence, product Terraform planning/apply, create-only deployment,
acceptance/independent verification, three separate runtimes and authenticated
Pub/Sub push. Every GitHub-federated principal is bound to the exact reusable
workflow at the immutable Slice A commit.

The Phase 4 verifier's retained Cloud Run role is narrowed with a provider-
supported individual-service IAM binding on the existing `phase4-proof` service
before any Phase 5 Cloud Run service can exist. The verifier custom role is
preserved without permission expansion and no project-level Cloud Run fallback
is introduced.

## Inert protected-main callers

Slice B adds manual-only callers for:

- product build;
- evidence adjudication;
- create-only deployment;
- independent verification;
- acceptance;
- product Terraform plan;
- product Terraform apply.

Each caller invokes only the corresponding reusable at
`67e61a6c0d4930f8a5c5db545ef84d8430e437bc`. The reusable controls independently
require `8ft0-ai/resilio`, protected `main`, and attempt 1 before OIDC.

No caller is triggered by push, pull request, schedule or workflow-run events.
Repository merge therefore does not itself perform a Terraform operation,
federate a Phase 5 principal, build an image, publish an artefact, deploy a
service or mutate runtime state.

## Maximum authority declared by Slice B

The declaration preserves separate authority domains:

- product planner/applier access to the existing private Terraform state bucket
  is limited to the `product/` state and lock plus
  `plan-evidence/product/`;
- product provider read/create permissions exclude IAM resources and remain
  constrained by the immutable Slice A candidate grammar;
- future Artifact Registry authority is declared only through the required
  identities/custom role; its final repository-level bindings are deferred until
  Slice C has created the exact `resilio-product` repository;
- product evidence-bucket authority remains condition-scoped to the supported
  Cloud Storage object resource names;
- the first product deployer has only `run.services.create`,
  `run.services.get` and `run.operations.get`, plus exact runtime
  `iam.serviceAccounts.actAs`;
- the ingest publisher custom role is declared, but its final topic-level grant
  is deferred until Slice C has created the exact
  `resilio-deployment-events` topic;
- processor can only create/read Firestore entities when the IAM condition
  matches the exact `projects/resilio-reference-e882d4/databases/(default)`
  database resource;
- API can only read Firestore entities under that same exact database boundary;
- the product Terraform applier can act as only `p5-pubsub-push`;
- the acceptance principal receives only its identity and custom metadata-read
  role definition in Slice B. It receives no project-level Cloud Run grant.

The resource-level Artifact Registry and standard Pub/Sub topic bindings are
deliberately absent because those targets do not exist until Slice C. They are
owned by the separately reviewed
`POST_SLICE_C_PRE_SLICE_D_RESOURCE_LEVEL_IAM_ACTIVATION` consequence, whose
allowed effect is limited to the exact `resilio-product` repository and
`resilio-deployment-events` topic grants accepted in amendment `5825076422`.

The service-scoped push-to-processor and acceptance ingest/API invocation
bindings are also deliberately absent because their Cloud Run targets do not
exist until Slice D. The Pub/Sub service-agent token-creation binding remains
absent. Those continue to belong to the separately reviewed post-create D.5 IAM
consequence.

## Consequence boundary

Merging this repository declaration does not create cloud authority. The first
Phase 5 cloud consequence remains the separately governed bootstrap transaction:

```text
fresh live preflight
-> one saved bootstrap plan
-> completely fresh exact-effect/security/authority review
-> owner apply authority
-> exact apply
-> independent/no-change reconciliation
```

That transaction is not authorised by Slice B repository implementation or
merge authority.

Praxis: `8ft0-ai/praxis@5af4740552c284008de09e1b6c0d1b5dad4c754b`

Core practice: `praxis/evidence-governed-change/v0.2`

Specialised practices: none.
