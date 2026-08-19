#!/usr/bin/env python3
"""Credential-free validation for the Phase 3 normal Terraform caller contract."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_CALLER_BLOBS = {
    ".github/workflows/terraform-foundation-plan.yml": "828eb68a9ccc722e8851608d30230f12b8dd4202",
    ".github/workflows/terraform-foundation-apply.yml": "09544cc89bcf91d61c102dd0f786ccb16c4a92f0",
    ".github/workflows/terraform-foundation-drift.yml": "c5122387465b154b930023f9c6810dcf2dc598e8",
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
