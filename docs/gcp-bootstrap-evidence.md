# GCP bootstrap evidence

This document records the non-sensitive canonical result of Resilio issue #6. The authoritative governance and execution history remains in the issue; private Terraform state, billing identifiers, credentials, raw IAM and owner-local diagnostics are deliberately excluded from Git.

## Canonical resource identities

The verified control plane uses:

- control project: `resilio-control-e882d4` (`400271474382`);
- reference project: `resilio-reference-e882d4` (`144158187163`);
- Terraform state bucket: `resilio-control-e882d4-tfstate`;
- Terraform backend prefix: `bootstrap`;
- default-workspace state object: `bootstrap/default.tfstate`;
- Workload Identity Provider: `projects/400271474382/locations/global/workloadIdentityPools/github/providers/resilio`;
- federation probe service account: `github-federation-probe@resilio-control-e882d4.iam.gserviceaccount.com`; and
- trusted GitHub OIDC subject: `repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main`.

The canonical non-sensitive backend configuration is committed in [`../infra/bootstrap/backend.tf`](../infra/bootstrap/backend.tf).

## Gate B verification

Gate B completed under the bounded issue authority and is durably recorded by issue #6 comment `5328190302`.

The final proof established:

- exactly one live GCS state object at `bootstrap/default.tfstate`;
- remote state lineage digest `fbd1f3dbf237286d69849680`, serial `27`, and exactly 16 managed addresses with address digest `6da48e48003412ab07acc715d8760d9ac9e2af81b24037db9c4ce16e507affb2`;
- the source bootstrap snapshot and remote state were semantically equal after excluding only Terraform serial/check-result representation metadata;
- a remote-backed Terraform plan returned `NO_CHANGE`;
- all retained same-lineage local Terraform state copies were removed after the remote no-change proof;
- Compute Engine API bootstrap side effects were cleaned up in both Resilio projects, with no Compute runtime retained;
- the unrelated owner sandbox service set remained unchanged;
- the state bucket, Workload Identity Federation, service-account/key/IAM and budget invariants remained within the approved boundary; and
- no private state or billing-account value was tracked in Git.

The monthly budget uses the billing account's native AUD currency with `budget_units = 10`, preserving the repository's US$10/month engineering ceiling based on the execution-time exchange-rate evidence recorded in the issue. No billing-account ID is committed.

## Gate C federation proof

The manual [`federation-smoke.yml`](../.github/workflows/federation-smoke.yml) workflow is deliberately not a deployment workflow. It is dispatch-only, fails unless the selected ref is exactly `refs/heads/main`, and has only `contents: read` plus `id-token: write`.

The workflow uses `google-github-actions/auth` pinned to immutable commit `7c6bc770dae815cd3e89ee6cdf493a5fab2cc093`. It requests a five-minute service-account access token through the canonical Workload Identity Provider, creates no credential file, exports no Google credential environment variables, calls no product/resource API and performs no cloud resource write. Successful token issuance is the bounded proof that trusted `main` can traverse the configured GitHub OIDC → Workload Identity Federation → probe-service-account path.

Because GitHub can only dispatch a workflow definition that already exists on the selected ref, the governed sequence is:

1. validate and freshly review the Gate C reconciliation PR while PR validation remains credential-free;
2. merge the exact approved candidate under the existing issue #6 merge authority;
3. dispatch the federation smoke only from the resulting `main`;
4. record the exact smoke run evidence; and
5. obtain a genuinely fresh independent final Gate C evidence review before closing issue #6.

The smoke adds no deployment authority. The probe service account remains without broad project resource roles or user-managed keys.
