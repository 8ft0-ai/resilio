#!/usr/bin/env python3
"""Credential-free validation for the temporary Slice D foundation-state initialiser."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/terraform-foundation-state-init.yml"
CONTROL_SEED = "cbfe9821ec07ca6c0c869ebe75100bc500c92a04"
APPLIER_REF = (
    "8ft0-ai/resilio/.github/workflows/terraform-apply-reusable.yml@"
    + CONTROL_SEED
)

REQUIRED = (
    "name: Terraform foundation state initialisation",
    "on:\n  workflow_dispatch:",
    "permissions:\n  contents: read",
    "concurrency:\n  group: terraform-foundation-state-initialisation\n  cancel-in-progress: false",
    'run: test "$GITHUB_REF" = "refs/heads/main"',
    "needs: require-main",
    "if: github.ref == 'refs/heads/main'",
    "permissions:\n      contents: read\n      id-token: write",
    f"uses: {APPLIER_REF}",
    "mode: initialise-empty-state",
    "candidate_sha: ${{ github.sha }}",
    "expected_main_sha: ${{ github.sha }}",
)

FORBIDDEN = (
    "pull_request:",
    "pull_request_target:",
    "\npush:",
    "\nschedule:",
    "workflow_run:",
    "${{ secrets.",
    "google-github-actions/auth@",
    "hashicorp/setup-terraform@",
    "actions/checkout@",
    "continue-on-error:",
    "pull-requests:",
)


def main() -> int:
    errors: list[str] = []
    if not WORKFLOW.is_file():
        errors.append(f"Slice D setup caller is missing: {WORKFLOW.relative_to(ROOT)}")
    else:
        text = WORKFLOW.read_text(encoding="utf-8")
        for required in REQUIRED:
            if required not in text:
                errors.append(f"Slice D setup caller missing required contract token: {required}")
        for forbidden in FORBIDDEN:
            if forbidden in text:
                errors.append(f"Slice D setup caller contains forbidden token: {forbidden.strip()}")
        if text.count("workflow_dispatch:") != 1:
            errors.append("Slice D setup caller must expose exactly one workflow_dispatch trigger")
        use_lines = [
            line.strip()[len("uses: "):]
            for line in text.splitlines()
            if line.strip().startswith("uses: ")
        ]
        if use_lines != [APPLIER_REF]:
            errors.append(
                "Slice D setup caller may invoke only the immutable trusted applier reusable workflow"
            )
        run_lines = [
            line.strip()[len("run: "):]
            for line in text.splitlines()
            if line.strip().startswith("run: ")
        ]
        if run_lines != ['test "$GITHUB_REF" = "refs/heads/main"']:
            errors.append(
                "Slice D setup caller may execute only the local trusted-main guard; "
                "Terraform/authentication must remain inside the immutable reusable workflow"
            )

    if errors:
        print("Slice D setup caller validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Slice D setup caller validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
