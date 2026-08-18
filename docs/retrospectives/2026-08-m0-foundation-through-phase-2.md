# M0 foundation through Phase 2 retrospective

Date: 2026-08-19

## Scope

This retrospective covers Resilio from the initial foundation documentation through repository governance, GitHub-side protection, the GCP bootstrap, Gate C verification, and post-slice branch housekeeping.

It records lessons from completed work. It does not by itself authorise Phase 3 implementation or change established architecture, security, cost, IAM, state, or repository-governance boundaries.

## Outcome

Resilio progressed from an empty public repository to a governed engineering system with documented architectural intent, protected change flow, reproducible credential-free CI, private remote Terraform state, keyless GitHub-to-GCP identity, bounded IAM, cost controls, and independently verified bootstrap evidence.

The work preserved the intended principle that the reference implementation should be enterprise-engineered rather than enterprise-sized. No application runtime, broad deployment permissions, long-lived Google Cloud credentials, or material recurring cost were introduced during the bootstrap phase.

## What worked well

### Architecture before infrastructure

The initial foundation work established the product direction, public/private boundary, monorepo approach, Terraform-state strategy, serverless-first reference architecture, resilience ambitions, and cost envelope before cloud infrastructure was introduced. Those constraints remained useful during implementation rather than becoming passive documentation.

### Engineering control plane before cloud control plane

Repository governance, `AGENTS.md`, pull-request conventions, baseline CI, immutable action pins, and GitHub protection were established before Terraform was permitted to mutate Google Cloud. The cloud bootstrap therefore operated inside an already-governed engineering system rather than relying on controls added afterwards.

### Independent review found real defects

Fresh substantive reviews and fail-closed gates detected issues that materially improved the result:

- the Terraform provider lock file initially lacked the package checksum required for the owner-local macOS execution environment;
- the bootstrap budget incorrectly assumed a hard-coded USD currency even though Google Cloud Billing requires the budget currency to match the billing account's native currency; and
- the initial Gate C validator relied too heavily on substring checks and was strengthened to enforce the intended workflow and backend contracts more exactly.

These were not ceremonial findings. Each prevented the workflow from accepting a weaker or incorrect state.

### Fail-closed behaviour

The bootstrap repeatedly stopped before unsafe or unjustified progression when assumptions were not satisfied. The macOS lockfile issue stopped before cloud mutation, the currency mismatch stopped the budget path, and Gate C stopped until its validator was strong enough. This is behaviour Resilio should later demonstrate in its own product and resilience controls.

### Security and cost boundaries held

The completed bootstrap preserved:

- private, versioned remote Terraform state outside Git;
- no long-lived service-account keys;
- immutable repository/main Workload Identity Federation claims;
- a deliberately least-privilege federation probe identity;
- credential-free public pull-request validation;
- trusted-main-only authentication proof;
- no cloud product write performed by the federation smoke test; and
- the established low-cost operating envelope.

### Completion included reconciliation and cleanup

Gate C evidence was reconciled back into Git and independently reviewed before Phase 2 was closed. Obsolete development branches were then audited and removed rather than being left as permanent repository clutter.

## Where the process was more expensive than necessary

Issue #6 accumulated a large amount of coordination and evidence history. Much of that was justified because it was the first slice combining Terraform state, IAM, billing, external execution, GitHub identity, and cloud mutation. However, exact base/head identities, validation runs, consumed authority, current gate, remediation state, and next permitted action were often reconstructed repeatedly from multiple records.

The controls were useful, but the state machine was more implicit than it should be. Future phases should preserve the guarantees while making the current governed state cheaper to reconstruct and progress.

Three implementation defects also exposed gaps in the design approach:

1. The missing Darwin checksum showed that reproducibility was designed before the supported execution-environment matrix was stated explicitly.
2. The budget-currency issue showed that an engineering policy expressed in USD had been coupled too directly to a provider representation that must use billing-account-native currency.
3. The Gate C validator showed that checking for textual symptoms is weaker than enforcing the invariant or contract that actually matters.

## Governance lesson

The governance system has now demonstrated that it can stop unsafe progression and surface real defects. From Phase 3 onward, the goal should not be to add more ceremony. The goal should be to make the existing controls inexpensive and increasingly machine-enforced.

A mature delivery system should automate routine transitions when policy, evidence, and authority make the next action objectively decidable, while reserving human judgement for genuine architecture, security, cost, risk, or authority decisions.

## Improvements to carry into Phase 3 planning

These are retrospective recommendations for the next planning activity; they are not implementation authority on their own.

### 1. Standardise a current-state evidence capsule

Use a consistent compact record for governed slices containing at least the governing issue, authoritative `main`, candidate base/head, authority consumed, validation identity, substantive review disposition, external evidence, and current/next gate. Fresh contexts must still verify primary evidence, but the capsule should provide a reliable index rather than requiring extensive comment archaeology.

### 2. State supported execution environments up front

Terraform and tooling changes should define and validate their execution matrix before an external gate. At the current stage this should include the GitHub Actions Linux runner and the intended owner-local macOS environment where local execution remains part of a governed workflow.

### 3. Encode invariants rather than textual symptoms

Repository validation should increasingly enforce properties such as trusted-main-only cloud identity, least-privilege permissions, credential-free pull-request checks, private backend shape, and cost/security boundaries rather than merely verifying that expected strings are present.

### 4. Separate engineering policy from provider representation

Stable domain policies such as cost ceilings, security boundaries, identity constraints, and lifecycle requirements should remain distinct from the concrete representation required by Google Cloud or another provider.

### 5. Automate governance plumbing

Exact-head checks, base freshness, validation-run identity, merged-tree equivalence, and evidence-capsule generation are candidates for repository automation so that reviewers and agents spend less effort manually reconstructing mechanically provable state.

### 6. Reduce recurring branch housekeeping

Automatic deletion of merged pull-request head branches is a sensible future repository-governance improvement. It should be considered under an appropriately bounded governance change rather than changed implicitly as part of this retrospective.

## What should remain unchanged

The following controls proved useful and should remain unless a later governed decision provides evidence for changing them:

- credential-free public pull-request CI separated from trusted-main cloud authority;
- private Terraform state outside Git;
- keyless workload identity and no long-lived service-account keys;
- explicit least privilege;
- immutable external action pins;
- fail-closed execution;
- exact-candidate substantive review where security-sensitive or otherwise required;
- explicit cost boundaries; and
- the rule that capability does not itself grant authority.

The phased delivery approach also remains valuable: build one real capability at a time and refine the next bounded phase from evidence rather than creating a speculative distant backlog.

## Related delivery records

- Foundation direction: PR #1.
- Repository governance and baseline CI: issue #2 / PR #3.
- GitHub-side repository protection: issue #4 / PR #5.
- GCP bootstrap and Gate C: issue #6, including PRs #7, #8, #9, and #11.
- Retrospective record: issue #12.

## Conclusion

The foundation controls worked and materially improved the implementation. The next engineering challenge is to make those controls cheap to operate.

**Retrospective theme: the controls worked; now make the controls cheap.**

Phase 3 should therefore treat the Terraform control model not only as plan/apply/drift automation, but as the point where Resilio begins turning manually exercised governance principles into a repeatable paved road.
