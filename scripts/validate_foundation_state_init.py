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
EXPECTED_WORKFLOW = f"""name: Terraform foundation state initialisation

on:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: terraform-foundation-state-initialisation
  cancel-in-progress: false

jobs:
  require-main:
    name: require-trusted-main
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - name: Require trusted main
        run: test \"$GITHUB_REF\" = \"refs/heads/main\"

  initialise:
    name: initialise-empty-foundation-state
    needs: require-main
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      pull-requests: read
      id-token: write
    uses: {APPLIER_REF}
    with:
      mode: initialise-empty-state
      candidate_sha: ${{{{ github.sha }}}}
      expected_main_sha: ${{{{ github.sha }}}}
"""


def main() -> int:
    if not WORKFLOW.is_file():
        print(
            f"Slice D setup caller validation failed: missing {WORKFLOW.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1

    try:
        text = WORKFLOW.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print("Slice D setup caller validation failed: workflow is not UTF-8", file=sys.stderr)
        return 1

    if text != EXPECTED_WORKFLOW:
        print(
            "Slice D setup caller validation failed: workflow must match the complete "
            "canonical one-time caller contract exactly",
            file=sys.stderr,
        )
        return 1

    print("Slice D setup caller validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
