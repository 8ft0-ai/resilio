# Contributing to Resilio

Resilio is an open-source operational intelligence and resilience verification project. Contributions should preserve the evidence-first, Git-driven and security-conscious engineering model described in `docs/`.

## Normal change flow

1. Start from a bounded issue or other explicit governing record for consequential work.
2. Make the minimum change needed to satisfy that objective.
3. Open a pull request that identifies the governing record, scope, validation and material security/cost implications.
4. Let mechanical checks run automatically.
5. Obtain substantive review when the governing record requires it.
6. Merge only with applicable authority and required checks satisfied.
7. Verify post-merge state when the change affects repository, deployment or runtime behaviour.

Routine mechanically decidable steps should not require repeated human confirmation. Human attention is reserved for substantive decisions, approval boundaries and exceptional actions.

## Pull requests

Keep pull requests bounded and reviewable. A PR should explain:

- the objective and governing issue;
- what changed and what deliberately did not;
- how the exact candidate was validated;
- security, authority, reliability or cost implications when material; and
- any known follow-up that is explicitly outside the current scope.

Do not mix unrelated cleanup or speculative future work into a governed change.

## Validation

Run repository-owned checks locally where practical before opening or updating a pull request. CI must not require contributor secrets or Google Cloud credentials for baseline repository validation.

Do not weaken validation to make a candidate pass. Fix the defect or record the genuine decision boundary.

## Architecture decisions

Consequential decisions that establish or materially change architecture, authority, security, cost or lifecycle boundaries should be captured as ADRs using `docs/adr/README.md`.

Not every implementation detail needs an ADR. Prefer the smallest durable decision record that future contributors will need to understand why a boundary exists.

## Security and secrets

Never commit real credentials, secret values, private keys or Terraform state. See `SECURITY.md` and `docs/security-and-private-state.md`.

If you discover a vulnerability or exposed secret, do not publish exploitable details in a public issue before the maintainer has had an opportunity to contain the risk.

## Cost discipline

The canonical reference deployment is intentionally constrained to a normal target of at most US$5/month and an engineering ceiling of US$10/month. Changes that introduce persistent billable resources or materially change cost assumptions require explicit treatment in the governing issue and review.
