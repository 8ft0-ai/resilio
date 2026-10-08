# Repository operating contract

This file defines repository-local operating expectations for contributors and engineering agents working in Resilio.

## Praxis engineering practice

For governed engineering work, use `https://github.com/8ft0-ai/praxis` as Resilio's linked engineering-practice source.

Praxis baseline: `5af4740552c284008de09e1b6c0d1b5dad4c754b`. Resolve this repository-selected baseline to one exact commit at the start of each new governed task, keep that task pin unchanged for the lifetime of the task, and start with `PRACTICE.md` from that exact commit.

Repository-local Resilio instructions and explicit task authority remain higher precedence. Updating the repository-selected Praxis baseline is a separate governed Resilio change and does not alter an already-running task pin.

## Authority and evidence

- Git is authoritative for desired state where state can reasonably be represented declaratively.
- GitHub issues, pull requests, reviews and repository records provide governance and operational intent.
- Capability is not authority. Access to mutate the repository, GitHub settings or cloud resources does not itself authorise that action.
- Treat stale summaries and handovers as navigation aids. Refresh decision-critical state before consequential actions.
- Prefer evidence from the exact candidate, commit, workflow run or runtime state being judged.
- Fail closed when required authority or decision-critical evidence cannot be established: do not perform the consequential mutation, and surface the unresolved boundary instead of inferring permission or state.

## Change discipline

- Work from a bounded governing issue or other explicit authority record when a change is consequential.
- Prefer the minimum safe change that satisfies the current objective.
- Do not expand a task into adjacent implementation merely because it appears useful.
- Preserve security, cost, evidence and lifecycle boundaries already established by accepted repository records.
- Keep secrets, credentials and private Terraform state out of Git.
- Do not introduce long-lived Google Cloud service-account keys.

## Owner-local reusable tooling

- For owner-local observation or evidence that cannot legitimately run in the remote assistant environment, prefer a stable, separately adopted `agentctl` named capability when it already covers the reusable mechanism required by the governed task.
- Do not generate or download a substantial bespoke shell/Python handoff, or add a Resilio wrapper that merely mirrors an adopted `agentctl` mechanism. Keep direct capability invocation small and keep project policy explicit.
- Resilio continues to own expected repository, Terraform and cloud identities, allowed or forbidden effects, authority, review gates and the decision about what may happen next. A successful `agentctl` result is evidence only and never grants Resilio mutation authority.
- Bind decision-critical use to the exact `agentctl` identity that Resilio has adopted for the task or pilot. Do not silently fall forward to floating upstream `main`, an unmerged capability or a later interface revision.
- If the adopted capability is insufficient or unavailable, preserve the normal fail-closed boundary and use only the minimum separately governed local mechanism needed for the task. Do not weaken Resilio controls or broaden authority merely to avoid an upstream gap.

## Autonomous progression

For one bounded governed objective, continue autonomously through all mechanically decidable internal stages when current authority and evidence make the next action safe. Routine planning, implementation, validation, bounded remediation and evidence capture should therefore proceed without repeated human confirmation.

Use this outcome-sized transaction pattern by default:

```text
orient
-> reconcile
-> prepare / implement
-> validate
-> bounded remediation
-> fresh substantive review where required
-> genuine owner consequence boundary
-> execute the exact authorised consequence
-> independently verify
-> terminal reconcile
```

An intermediate artefact, validation result, review, merge, saved plan, reconciliation or readiness check does not by itself require a human or session stop. Continue when the next action is mechanically decidable under current authority. A merge or other consequence still requires separate owner authority when the governing record says so.

Keep objectively clear bounded remediation inside the same transaction when it does not materially change scope, architecture, authority or external consequence. Any candidate subject to a review gate must still be reviewed at its final exact identity after applicable remediation.

Escalate only when a genuine human decision or authority boundary is reached, including a failed invariant, material scope or architecture change, permission broadening, security weakening, destructive or production action, material cost commitment, acceptance of a known failed control, or an ambiguous external consequence.

## Review independence

When a governing issue requires a genuinely fresh independent substantive review, the authoring context must not substitute its own conclusion for that review. A fresh reviewer must reconstruct the exact candidate and decision-critical evidence directly.

A review disposition does not by itself grant merge authority unless the governing record explicitly says so.

## Review/fix loop circuit-breaker pilot

Issue #120 pilots a Resilio-local circuit breaker for repeated fresh-review/remediation loops. This section is repository-local only and does not change Praxis, Switchboard or any other repository.

Set `REVIEW_FIX_LOOP_DETECTED=TRUE` for one governed transaction when either:

- a fresh substantive review after remediation discovers a new material blocker in architecture, authority, identity, currentness or supersession, positive reachability, permission envelopes, external-platform semantics, or terminal provenance that was not in the prior defect set; or
- two consecutive fresh substantive reviews of the same governed transaction require remediation.

A plainly bounded implementation defect such as a typo, an omitted local test case or a mechanically obvious API misuse does not by itself trigger the circuit breaker unless it exposes one of the systemic categories above.

Before closure work begins, record `REVIEW_FIX_LOOP_DETECTED` durably on the governing issue. Bind that activation record to the triggering review or reviews, the affected PR/candidate identity, the prior remediation identity where applicable, and `NEXT_PHASE=ARCHITECTURE_CLOSURE`. Later sessions must treat that durable record, not an inferred historical pattern alone, as the transaction-level activation state.

While the circuit breaker is active:

- do not remediate only the latest systemic finding before architecture closure; a `/fix` request routes to closure first;
- freeze implementation except for artefacts required to complete the closure analysis;
- reconstruct the complete affected lifecycle and produce, at minimum, a canonical identity DAG, authority/permission producer-to-consumer matrix, global transition matrix, currentness/supersession model, adversarial/interleaving matrix, positive-reachability proof, terminal-provenance check, and complete material defect set;
- record the closure artefact durably and treat its complete systemic defect set as the frozen remediation scope;
- remediate that frozen set together in one encompassing candidate where technically coherent;
- a plainly bounded implementation defect discovered during that remediation may be corrected only when it does not change the closure model, architecture, authority, scope or external consequence; record it with the candidate-readiness evidence rather than silently expanding the frozen systemic set;
- before requesting another fresh substantive review, perform a closure-based candidate-readiness check against every frozen row and record the result.

If the next fresh substantive review discovers another new systemic blocker, keep the circuit breaker active, treat the closure model itself as incomplete, and return to architecture closure instead of patching the new finding directly. If it identifies only an incomplete implementation of an already frozen row or a plainly bounded non-systemic defect, remediation may continue within the frozen closure model and must again pass candidate readiness and fresh substantive review.

## Architecture-closure non-convergence

This Resilio-local second-level breaker applies only while `REVIEW_FIX_LOOP_DETECTED=true` and architecture closure is the active required phase for one governed transaction. It does not replace, clear or weaken the first-level circuit breaker.

Count consecutive genuinely fresh substantive reviews of exact architecture-closure candidates **within the same transaction and architecture family** that each require changes because of a newly identified material systemic defect in the closure model, identity, authority, provider semantics, positive reachability or terminal provenance. Count only durable exact closure/review identities and named newly discovered invariants. A bounded typo, missed local test, incomplete implementation of an already-frozen obligation, another transaction, or another architecture family cannot qualify. Missing or ambiguous counting evidence fails closed rather than establishing a trigger.

After **two consecutive qualifying reviews**, durably record `ARCHITECTURE_NONCONVERGENCE_DETECTED` on the governing issue, identifying both review IDs, both exact closure candidates, the common architecture family and each new systemic invariant. Freeze further incremental architecture amendments, ordinary `/fix` and implementation until an owner-approved architecture disposition. Do not restart the count merely by renaming a revision or starting a new session.

Perform one bounded, read-only `RETAIN | RADICALLY_SIMPLIFY | REMOVE` assessment of the architecture, rather than fixing only the latest finding. Assess the actual required safety property, provider evidence and trust boundary, authority and positive reachability, cumulative proof complexity, feasible alternatives, and whether each alternative resolves the motivating case using evidence actually available. Preserve negative evidence and compare the three options explicitly:

- **RETAIN:** require a concrete justification that the current abstraction can satisfy the property and a finite maximum number of further closure attempts; otherwise remain blocked.
- **RADICALLY_SIMPLIFY:** remove unjustified proof or exception machinery while preserving established fail-closed safety and authority constraints.
- **REMOVE:** retire the non-converging abstraction and restore the applicable fail-closed boundary; do not infer a bypass or grant an exemption.

Record an explicit owner disposition before any further architecture amendment or implementation. The disposition cannot itself authorise repository code/policy changes, merge, risk acceptance, deletion or lifecycle control, credential changes, workflow dispatch or cloud effects; these require their separately applicable gates. An unresolved external-provider anomaly may legitimately leave the transaction blocked; it must not be converted into evidence of harmlessness or an admission exception.

The existing `REVIEW_FIX_LOOP_DETECTED` activation and `REVIEW_FIX_LOOP_CLEARED` semantics remain unchanged. This second-level disposition never clears the circuit breaker: only a blocker-free genuinely fresh substantive review plus the existing durable clearing record can do so. Historical pilot decisions remain historical and are not retroactively reclassified.

Clear the transaction-level circuit breaker only after a fresh substantive review reports no material blockers. Record `REVIEW_FIX_LOOP_CLEARED` durably on the governing issue, binding the activation record, final closure artefact, exact reviewed candidate and passing review. Historical activation/closure records remain evidence and must not be interpreted as an active circuit breaker after this explicit clearing record.

The first live pilot is issue #109 / PR #119. At that pilot's next stable review boundary, record a repository-local `RETAIN`, `AMEND` or `REJECT` disposition covering the trigger quality, closure usefulness, remediation convergence and whether the subsequent fresh review exposed any new systemic blocker. Any wider adoption is a separate governed change.

## Validation

- Run repository-owned mechanical validation before requesting substantive review.
- Validation must be reproducible and tied to the exact candidate revision where practical.
- Do not weaken tests, checks or acceptance criteria merely to obtain a passing result.
- A bounded defect with an objectively clear minimum-safe fix may be remediated within the existing scope; materially changed candidates still require any review gates applicable to the new revision.

## Cloud and runtime boundaries

Repository work must preserve the foundation documented in `docs/`:

- serverless/scale-to-zero reference architecture by default;
- private remote Terraform state split by bounded lifecycle/authority domains;
- secrets outside Git and normally outside Terraform state;
- short-lived federated identity for GitHub-to-Google Cloud access;
- normal reference-cost target of at most US$5/month and engineering ceiling of US$10/month;
- GKE Autopilot reserved for bounded ephemeral resilience experiments unless a later accepted decision changes that direction.

## Break glass

Manual emergency mutation is exceptional. It must be narrowly scoped, auditable and subsequently reconciled to authorised Git state or explicitly reversed.
