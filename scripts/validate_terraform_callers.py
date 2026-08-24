#!/usr/bin/env python3
"""Credential-free validation for the normal Terraform caller contract."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_CALLER_BLOBS = {
    ".github/workflows/terraform-foundation-plan.yml": "00194171b7fff6388ce11e19aca02b1de2c48ae5",
    ".github/workflows/terraform-foundation-apply.yml": "725cd32228001a670331dfe88ae1c30fa1b4980b",
    ".github/workflows/terraform-foundation-drift.yml": "37efd7451bfdf2f593242ca18e024d024bb514be",
}

RETIRED_SETUP_PATHS = (
    ".github/workflows/terraform-foundation-state-init.yml",
    "scripts/validate_foundation_state_init.py",
)

VALIDATE_WORKFLOW = ROOT / ".github/workflows/validate.yml"


def git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    prefix = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(prefix + content).hexdigest()


def main() -> int:
    errors: list[str] = []

    for relative, expected_sha in EXPECTED_CALLER_BLOBS.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"required normal Terraform caller is missing: {relative}")
            continue
        actual_sha = git_blob_sha(path)
        if actual_sha != expected_sha:
            errors.append(
                f"normal Terraform caller {relative} must remain at reviewed blob "
                f"{expected_sha}; found {actual_sha}"
            )

    for relative in RETIRED_SETUP_PATHS:
        if (ROOT / relative).exists():
            errors.append(f"retired one-time foundation setup path must be absent: {relative}")

    if not VALIDATE_WORKFLOW.is_file():
        errors.append("repository validation workflow is missing")
    else:
        validate_text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        if "python3 scripts/validate_terraform_callers.py" not in validate_text:
            errors.append("repository workflow must invoke normal Terraform caller validation")
        if "validate_foundation_state_init.py" in validate_text:
            errors.append("repository workflow must not invoke the retired foundation-state initialiser validator")

    if errors:
        print("Terraform caller validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Terraform caller validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
