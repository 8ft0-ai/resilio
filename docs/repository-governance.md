# Repository governance controls

This document distinguishes controls expressed in repository files from GitHub-hosted settings that must be configured and verified separately.

## Repository-owned controls

The repository currently defines:

- `AGENTS.md` for repository-local operating expectations;
- `CONTRIBUTING.md` for the normal governed change lifecycle;
- `SECURITY.md` for vulnerability and secret-exposure handling;
- `docs/adr/README.md` for consequential decision records;
- issue and pull-request templates for traceable change intent; and
- `.github/workflows/validate.yml` plus `scripts/validate_repo.py` for credential-free baseline mechanical validation.

These files are authoritative only for what they actually express. They do not by themselves prove that GitHub-side repository settings are enabled.

## Established GitHub-side controls

M0 Slice 2 / issue #4 established the current minimum GitHub-hosted change boundary for `main`.

The active repository branch ruleset is:

- ruleset ID `20908611`;
- name `main-governance`;
- target `~DEFAULT_BRANCH`;
- enforcement `active`;
- no bypass actors and no current-user bypass;
- deletion protection enabled;
- non-fast-forward protection enabled;
- pull requests required before changes reach `main`;
- formal approving-review count `0`, preserving the single-maintainer fresh-context review model without inventing a distinct reviewer identity; and
- required status check `repository` with strict required-status policy enabled.

Current GitHub branch evidence reports `main` as protected.

Repository-level Actions defaults are configured as:

- default `GITHUB_TOKEN` workflow permissions: `read`;
- Actions approval of pull-request reviews: disabled.

Repository security controls verified by owner-authenticated GitHub API evidence are:

- secret scanning enabled;
- secret-scanning push protection enabled;
- Dependabot security updates enabled; and
- vulnerability alerts enabled.

Optional non-provider secret patterns and secret validity checks remain disabled; this slice did not broaden scope merely to enable every available security feature.

## Review and authority model

GitHub protection enforces the mechanical merge boundary, but it does not replace repository governance.

The ruleset deliberately requires zero formal approving reviews because this is currently a single-maintainer repository. Where a governing issue requires genuinely fresh independent substantive review, that independence is provided by a fresh reasoning context and durable repository evidence rather than by inventing a second GitHub identity.

A review disposition still does not itself grant merge authority unless the governing record explicitly does so.

## Evidence record

The implementation plan and exact owner-approved settings are recorded in issue #4 comment `5307258240`.

The owner-local settings execution and API readback are recorded in issue #4 comment `5307287267`. That evidence includes the exact ruleset identity, Actions defaults, repository security settings and vulnerability-alert verification.

The ruleset and protected-branch state are also independently readable through the GitHub API. Administration-only Actions/security endpoints may require owner/admin-capable credentials; where an integration cannot read them, their state must not be inferred.

Configuration screenshots or prose assertions alone are not sufficient evidence for these controls.

## Change discipline

Future changes to branch protection, rulesets, Actions permissions, secret protection or equivalent repository-governance settings are consequential governance/security mutations. They require a bounded governing record, exact current-state evidence and authority appropriate to the change.

Do not weaken these controls merely to unblock a change. Any exceptional bypass or suspension is break-glass activity and must be narrowly authorised, auditable and reconciled afterwards.

## Scope boundary

This repository-governance slice does not create Google Cloud resources, Terraform state, workload identity, deployment authority or product code. Those belong to later M0 slices after the repository change boundary is proven.
