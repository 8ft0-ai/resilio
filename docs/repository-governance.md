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

These files are authoritative only for what they actually express. They do not prove that GitHub-side repository settings are enabled.

## GitHub-side controls to establish and verify

Before relying on `main` as a protected change boundary, repository settings should be configured and evidence captured for the intended minimum controls, including:

- require pull requests before changes reach `main`;
- require the baseline validation check to pass before merge;
- prevent accidental deletion or force-push of `main` unless a later explicit break-glass policy allows it;
- enable appropriate secret-scanning and push-protection capabilities available to the repository;
- keep default GitHub Actions token permissions at least privilege; and
- avoid granting workflows write authority unless a specific governed workflow requires it.

The exact GitHub ruleset or branch-protection mechanism should be selected from current platform capabilities when that control is implemented. This document deliberately does not claim those settings are active merely because the desired policy is written here.

## Evidence requirement

A later M0 step that establishes GitHub-side protection should record the exact settings/ruleset identity and verify behaviour from current GitHub state. Configuration screenshots or prose assertions alone are weaker than API/settings evidence tied to the repository.

## Scope boundary

This repository-governance slice does not create Google Cloud resources, Terraform state, workload identity, deployment authority or product code. Those belong to later M0 slices after the repository change boundary is proven.
